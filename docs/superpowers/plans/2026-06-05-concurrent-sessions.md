# Concurrent Sessions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Multiple sessions run concurrently with independent agent trees, each session's master + subagents execute in parallel via asyncio coroutines.

**Architecture:** New `SessionManager` owns multiple `SessionSlot` instances, each with its own `AgentManager` (renamed from `SubagentManager`). Only the active session streams events to the frontend; background sessions persist silently to disk.

**Tech Stack:** Python asyncio, WebSocket, Vue 3 + Pinia

---

## File Structure

| File | Responsibility |
|------|---------------|
| `agentcore/subagent_manager.py` | Rename `SubagentManager` → `AgentManager`, `_SubagentHandler` → `_AgentHandler` |
| `agentcore/session_manager.py` | **NEW** — `SessionSlot` dataclass + `SessionManager` class |
| `agentcore/ws_server.py` | Replace direct `SubagentManager` usage with `SessionManager`; route messages per-slot |
| `agentcore/agent.py` | No rename needed (uses `_subagent_manager` internally — rename to `_agent_manager`) |
| `agentcore/flet_ui/app.py` | Rename references |
| `agentcore/agent_sidebar.py` | Rename docstring reference |
| `ui/src/stores/session.ts` | Add `sessionStatuses`, `switchSession` |
| `ui/src/App.vue` | Handle `session_status`, `active_session_switched` events |
| `ui/src/components/SessionList.vue` | Show status dots per session |
| `tests/test_session_manager.py` | **NEW** — tests for SessionManager |

---

### Task 1: Rename SubagentManager → AgentManager

**Files:**
- Modify: `agentcore/subagent_manager.py`
- Modify: `agentcore/ws_server.py:1,19,634,648,659,666,668,856,1061`
- Modify: `agentcore/agent.py:147,148,150`
- Modify: `agentcore/flet_ui/app.py:27,40,43,44,47,68,70,73,78,81,86,811,813,876,877,879,880,884,887,988,990,993,1002,1008,1074,1076`
- Modify: `agentcore/agent_sidebar.py:74`
- Modify: `agentcore/tests/test_subagent_system.py:44,45,46,59`

- [ ] **Step 1: Rename in subagent_manager.py**

In `agentcore/subagent_manager.py`:
- Replace `class _SubagentHandler` with `class _AgentHandler` (line 88)
- Replace `class SubagentManager` with `class AgentManager` (line 338)
- Replace `def __init__(self, manager: "SubagentManager"` with `def __init__(self, manager: "AgentManager"` (line 97)
- Replace `handler = _SubagentHandler(self, "master")` with `handler = _AgentHandler(self, "master")` (line 366)
- Replace `handler = _SubagentHandler(self, agent_id)` with `handler = _AgentHandler(self, agent_id)` (line 416)
- Replace `[SubagentMgr]` with `[AgentMgr]` in all print statements (lines 474, 486, 494)
- Replace `"""SubagentManager — manages` with `"""AgentManager — manages` in module docstring (line 1)

- [ ] **Step 2: Rename in ws_server.py**

- Replace `from agentcore.subagent_manager import SubagentManager, _SubagentHandler` with `from agentcore.subagent_manager import AgentManager, _AgentHandler` (line 19)
- Replace docstring `"""WebSocket server — bridges frontend <-> SubagentManager.` with `"""WebSocket server — bridges frontend <-> AgentManager.` (line 1)
- Replace all `SubagentManager` type annotations with `AgentManager` (lines 634, 648, 659)
- Replace `SubagentManager(config, user_agents)` with `AgentManager(config, user_agents)` (line 1061)
- Replace all `_SubagentHandler` with `_AgentHandler` (lines 666, 668, 856)

- [ ] **Step 3: Rename in agent.py**

- Replace `"""Update agents_text from the SubagentManager if available."""` with `"""Update agents_text from the AgentManager if available."""` (line 147)
- Replace `self._subagent_manager` with `self._agent_manager` everywhere in the file (lines 148, 150)

- [ ] **Step 4: Rename in agent.py references from subagent_manager.py**

In `agentcore/subagent_manager.py`, replace:
- `controller.agent._subagent_manager = self` → `controller.agent._agent_manager = self` (lines 384, 426)

- [ ] **Step 5: Rename in flet_ui/app.py**

- Replace `from agentcore.subagent_manager import SubagentManager` with `from agentcore.subagent_manager import AgentManager` (line 27)
- Replace all `self.subagent_manager` with `self.agent_manager` (all occurrences)
- Replace all `SubagentManager(` with `AgentManager(` (lines 43, 879)
- Update comment on line 40: `SubagentHandler` → `AgentHandler`

- [ ] **Step 6: Rename in agent_sidebar.py**

- Replace `SubagentManager` in docstring (line 74)

- [ ] **Step 7: Rename in test file**

In `agentcore/tests/test_subagent_system.py`:
- Replace `from agentcore.subagent_manager import SubagentManager` with `from agentcore.subagent_manager import AgentManager`
- Replace `SubagentManager` with `AgentManager` in all test names, docstrings, and code (lines 44, 45, 59)

- [ ] **Step 8: Run all tests**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All 43+ tests pass (rename only, no logic change)

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: rename SubagentManager → AgentManager, _SubagentHandler → _AgentHandler"
```

---

### Task 2: Create SessionManager

**Files:**
- Create: `agentcore/session_manager.py`
- Create: `tests/test_session_manager.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_session_manager.py`:

```python
# tests/test_session_manager.py
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from agentcore.data_dir import DataDir
from agentcore.session_store import SessionStore
from agentcore.config import AgentConfig


def _make_config():
    return AgentConfig(provider="glm", model="test-model", api_key="fake")


def _make_store(tmp_dir: str):
    dd = DataDir(Path(tmp_dir) / ".ai-code-agent")
    dd.init()
    return SessionStore(dd), dd


@patch("agentcore.session_manager.AgentManager")
def test_create_session_creates_slot(MockManager):
    """create_session creates a SessionSlot with its own AgentManager."""
    from agentcore.session_manager import SessionManager
    mock_mgr = MagicMock()
    mock_mgr.agents = {"master": MagicMock(controller=MagicMock(agent=MagicMock()))}
    MockManager.return_value = mock_mgr

    with tempfile.TemporaryDirectory() as tmp:
        store, dd = _make_store(tmp)
        sm = SessionManager(config=_make_config(), store=store, dd=dd, ws=MagicMock())
        sid = store.create_session(r"D:\test", title="Test")
        sm.create_session(r"D:\test", sid, title="Test")

        assert sid in sm.slots
        assert sm.active_session_id == sid
        MockManager.assert_called_once()


@patch("agentcore.session_manager.AgentManager")
def test_load_session_restores_messages(MockManager):
    """load_session creates slot and restores persisted messages."""
    from agentcore.session_manager import SessionManager
    mock_mgr = MagicMock()
    mock_agent = MagicMock()
    mock_mgr.agents = {"master": MagicMock(controller=MagicMock(agent=mock_agent))}
    MockManager.return_value = mock_mgr

    with tempfile.TemporaryDirectory() as tmp:
        store, dd = _make_store(tmp)
        sm = SessionManager(config=_make_config(), store=store, dd=dd, ws=MagicMock())
        sid = store.create_session(r"D:\test", title="Test")
        store.append_message(r"D:\test", sid, {"role": "user", "content": "Hi"})

        sm.load_session(r"D:\test", sid)

        assert sid in sm.slots
        mock_agent.restore_messages.assert_called_once()
        msgs = mock_agent.restore_messages.call_args[0][0]
        assert len(msgs) == 1
        assert msgs[0]["content"] == "Hi"


@patch("agentcore.session_manager.AgentManager")
def test_switch_session_changes_active(MockManager):
    """switch_session changes active_session_id."""
    from agentcore.session_manager import SessionManager
    mock_mgr1 = MagicMock()
    mock_mgr1.agents = {"master": MagicMock(controller=MagicMock(agent=MagicMock()))}
    mock_mgr2 = MagicMock()
    mock_mgr2.agents = {"master": MagicMock(controller=MagicMock(agent=MagicMock()))}
    MockManager.side_effect = [mock_mgr1, mock_mgr2]

    with tempfile.TemporaryDirectory() as tmp:
        store, dd = _make_store(tmp)
        sm = SessionManager(config=_make_config(), store=store, dd=dd, ws=MagicMock())
        s1 = store.create_session(r"D:\test", title="S1")
        s2 = store.create_session(r"D:\test", title="S2")

        sm.create_session(r"D:\test", s1, title="S1")
        sm.create_session(r"D:\test", s2, title="S2")

        assert sm.active_session_id == s2
        sm.switch_session(s1)
        assert sm.active_session_id == s1


@patch("agentcore.session_manager.AgentManager")
def test_destroy_session_removes_slot(MockManager):
    """destroy_session kills agents and removes the slot."""
    from agentcore.session_manager import SessionManager
    mock_mgr = MagicMock()
    mock_mgr.agents = {"master": MagicMock(controller=MagicMock(agent=MagicMock()))}
    MockManager.return_value = mock_mgr

    with tempfile.TemporaryDirectory() as tmp:
        store, dd = _make_store(tmp)
        sm = SessionManager(config=_make_config(), store=store, dd=dd, ws=MagicMock())
        sid = store.create_session(r"D:\test", title="Test")
        sm.create_session(r"D:\test", sid, title="Test")

        assert sid in sm.slots
        sm.destroy_session(sid)
        assert sid not in sm.slots


@patch("agentcore.session_manager.AgentManager")
def test_get_active_returns_current_slot(MockManager):
    """get_active returns the slot for active_session_id."""
    from agentcore.session_manager import SessionManager
    mock_mgr = MagicMock()
    mock_mgr.agents = {"master": MagicMock(controller=MagicMock(agent=MagicMock()))}
    MockManager.return_value = mock_mgr

    with tempfile.TemporaryDirectory() as tmp:
        store, dd = _make_store(tmp)
        sm = SessionManager(config=_make_config(), store=store, dd=dd, ws=MagicMock())
        sid = store.create_session(r"D:\test", title="Test")
        sm.create_session(r"D:\test", sid, title="Test")

        active = sm.get_active()
        assert active is not None
        assert active.session_id == sid


def test_get_active_returns_none_when_empty():
    """get_active returns None when no sessions exist."""
    from agentcore.session_manager import SessionManager
    with tempfile.TemporaryDirectory() as tmp:
        store, dd = _make_store(tmp)
        sm = SessionManager(config=_make_config(), store=store, dd=dd, ws=MagicMock())
        assert sm.get_active() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_session_manager.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agentcore.session_manager'`

- [ ] **Step 3: Create SessionManager**

Create `agentcore/session_manager.py`:

```python
# agentcore/session_manager.py
"""SessionManager — manages concurrent sessions, each with its own AgentManager."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from agentcore.config import AgentConfig
from agentcore.data_dir import DataDir
from agentcore.session_store import SessionStore
from agentcore.subagent_manager import AgentManager

if TYPE_CHECKING:
    from websockets.asyncio.server import ServerConnection
    from agentcore.ws_server import WsEventHandler


@dataclass
class SessionSlot:
    """One active session: its own AgentManager + event handler."""
    session_id: str
    project_path: str
    agent_manager: AgentManager
    handler: "WsEventHandler"
    store: SessionStore


class SessionManager:
    """Manages all active sessions. Created once in run_ws_server()."""

    def __init__(self, config: AgentConfig, store: SessionStore,
                 dd: DataDir, ws: "ServerConnection"):
        self.slots: dict[str, SessionSlot] = {}
        self.active_session_id: str = ""
        self._config = config
        self._store = store
        self._dd = dd
        self._ws = ws

    async def create_session(self, project_path: str, session_id: str,
                              title: str = "New Chat") -> str:
        """Create new slot with its own AgentManager, bind store."""
        from agentcore.agent_definitions import load_user_agents
        from agentcore.ws_server import WsEventHandler

        user_agents = load_user_agents(self._config.cwd)
        mgr = AgentManager(self._config, user_agents)

        # Connect MCP for master
        master_state = mgr.agents["master"]
        await master_state.controller.connect_mcp()

        handler = WsEventHandler(self._ws, master_state.controller)
        handler._store = self._store
        handler._session_project = project_path
        handler._session_id = session_id

        # Bind agent for message persistence
        master_state.controller.agent.bind_session(
            self._store, project_path, session_id)
        master_state.controller.agent.messages = []

        # Wire controller handler
        master_state.controller.handler = handler
        mgr.master_handler = handler

        # Wire on_change
        import asyncio
        async def _push_agent_list():
            from agentcore.ws_server import _send_agent_list
            await _send_agent_list(self._ws, mgr)
        mgr.on_change = lambda: asyncio.ensure_future(_push_agent_list())

        slot = SessionSlot(
            session_id=session_id,
            project_path=project_path,
            agent_manager=mgr,
            handler=handler,
            store=self._store,
        )
        self.slots[session_id] = slot
        self.active_session_id = session_id
        return session_id

    async def load_session(self, project_path: str, session_id: str):
        """Create slot and restore messages + debug entries from disk."""
        from agentcore.agent_definitions import load_user_agents
        from agentcore.ws_server import WsEventHandler

        user_agents = load_user_agents(self._config.cwd)
        mgr = AgentManager(self._config, user_agents)

        master_state = mgr.agents["master"]
        await master_state.controller.connect_mcp()

        handler = WsEventHandler(self._ws, master_state.controller)
        handler._store = self._store
        handler._session_project = project_path
        handler._session_id = session_id

        # Restore persisted messages and debug entries
        messages = self._store.load_messages(project_path, session_id)
        debug_entries = self._store.load_debug_log(project_path, session_id)

        master_state.controller.agent.bind_session(
            self._store, project_path, session_id)
        master_state.controller.agent.restore_messages(messages)
        handler._debug_entries = list(debug_entries)

        master_state.controller.handler = handler
        mgr.master_handler = handler

        import asyncio
        async def _push_agent_list():
            from agentcore.ws_server import _send_agent_list
            await _send_agent_list(self._ws, mgr)
        mgr.on_change = lambda: asyncio.ensure_future(_push_agent_list())

        slot = SessionSlot(
            session_id=session_id,
            project_path=project_path,
            agent_manager=mgr,
            handler=handler,
            store=self._store,
        )
        self.slots[session_id] = slot
        self.active_session_id = session_id

    async def destroy_session(self, session_id: str):
        """Kill all agents in slot, remove slot."""
        slot = self.slots.pop(session_id, None)
        if not slot:
            return
        mgr = slot.agent_manager
        # Kill all non-master agents
        for aid in list(mgr.agents.keys()):
            if aid != "master":
                await mgr.kill(aid)
        # Cancel master if running
        await mgr.agents["master"].controller.cancel()
        if self.active_session_id == session_id:
            self.active_session_id = ""

    def switch_session(self, session_id: str) -> bool:
        """Change active session. Returns True if switched."""
        if session_id not in self.slots:
            return False
        self.active_session_id = session_id
        return True

    def get_active(self) -> "SessionSlot | None":
        """Get the currently viewed session slot."""
        return self.slots.get(self.active_session_id)

    def get_aggregate_status(self, session_id: str) -> str:
        """Get aggregate status for a session: running, idle, or error."""
        slot = self.slots.get(session_id)
        if not slot:
            return "idle"
        has_running = False
        has_error = False
        for aid, state in slot.agent_manager.agents.items():
            if state.status == "running":
                has_running = True
            elif state.status == "failed":
                has_error = True
        if has_running:
            return "running"
        if has_error:
            return "error"
        return "idle"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_session_manager.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add agentcore/session_manager.py tests/test_session_manager.py
git commit -m "feat: add SessionManager — concurrent session lifecycle management"
```

---

### Task 3: Wire WsEventHandler to SessionManager

**Files:**
- Modify: `agentcore/ws_server.py` (WsEventHandler.__init__, _send, _send_debug)

- [ ] **Step 1: Add _session_manager attribute to WsEventHandler**

In `agentcore/ws_server.py`, modify `WsEventHandler.__init__`:

```python
def __init__(self, ws: ServerConnection, controller: AgentController):
    self._ws = ws
    self._controller = controller
    self._pending_request_data = None
    self._pending_tool_calls: list[dict] = []
    self._has_pending_tool_results = False
    self._debug_entries: list[dict] = []
    self._entry_id = 0
    self._store: "SessionStore | None" = None
    self._session_project: str = ""
    self._session_id: str = ""
    self._session_manager: "SessionManager | None" = None
```

- [ ] **Step 2: Modify _send to check active session**

Replace the `_send` method:

```python
async def _send(self, data: dict):
    """Send to frontend only if this handler's session is active."""
    if self._session_manager and self._session_id:
        if self._session_manager.active_session_id != self._session_id:
            return  # Background session — don't stream to frontend
    try:
        payload = json.dumps(data, ensure_ascii=False)
        await self._ws.send(payload)
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        print(f"[ws_server] _send error: {e}")
```

- [ ] **Step 3: Modify _send_debug to send session_status for background sessions**

In the `_send_debug` method, after the persist block, add notification for background completion:

```python
# Notify frontend about background session status changes
if self._session_manager and self._session_id:
    if self._session_manager.active_session_id != self._session_id:
        status = self._session_manager.get_aggregate_status(self._session_id)
        try:
            await self._ws.send(json.dumps({
                "type": "session_status",
                "session_id": self._session_id,
                "status": status,
            }, ensure_ascii=False))
        except Exception:
            pass
```

- [ ] **Step 4: Run all tests**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add agentcore/ws_server.py
git commit -m "feat: WsEventHandler respects active session — background sessions silent"
```

---

### Task 4: Refactor ws_server to use SessionManager

**Files:**
- Modify: `agentcore/ws_server.py` (run_ws_server, _handle_client, message handlers)

This is the largest task. The key changes:
1. `run_ws_server` creates `SessionManager` instead of `AgentManager`
2. `_handle_client` gets `session_mgr: SessionManager` instead of `manager: AgentManager`
3. Session-related messages (`create_session`, `load_session`, `switch_session`) route through `SessionManager`
4. Non-session messages (`send_message`, `cancel`, etc.) route through active slot's `AgentManager`

- [ ] **Step 1: Update run_ws_server**

Replace the `run_ws_server` function to create `SessionManager`:

```python
async def run_ws_server(config: AgentConfig, port: int = 18765,
                         reload: bool = False, data_dir: str | None = None):
    """Start WebSocket server. Called from main.py --ws mode."""
    from agentcore.session_manager import SessionManager

    effective_data_dir = data_dir or str(Path(__file__).parent.parent / ".ai-code-agent")
    dd = DataDir(Path(effective_data_dir))
    dd.init()
    store = SessionStore(dd)

    watch_root = Path(__file__).parent

    while True:
        # SessionManager is created per server lifecycle (not per session)
        # We pass a placeholder ws that gets updated on each connection
        session_mgr = SessionManager(config=config, store=store, dd=dd, ws=None)

        async def handler(websocket: ServerConnection):
            session_mgr._ws = websocket
            await _handle_client(websocket, session_mgr, store, dd)

        logger.info(f"WebSocket server listening on ws://127.0.0.1:{port}")
        print(f"WebSocket server listening on ws://127.0.0.1:{port}")
        if reload:
            print("[reload] watching for changes in agentcore/")

        server_task = asyncio.create_task(
            _serve_forever(handler, port)
        )
        if reload:
            watch_task = asyncio.create_task(_watch_files(watch_root))
            done, _ = await asyncio.wait(
                [server_task, watch_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in [server_task, watch_task]:
                if not t.done():
                    t.cancel()
            if watch_task in done:
                print("[reload] restarting server...")
                await asyncio.sleep(0.5)
                continue
            break
        else:
            await server_task
            break
```

- [ ] **Step 2: Update _handle_client signature and initial connection**

Replace `_handle_client` to work with `SessionManager`:

```python
async def _handle_client(websocket: ServerConnection, session_mgr: SessionManager,
                          store: "SessionStore", dd: "DataDir"):
    """Handle a single WebSocket client connection."""
    # Send connection message (no session active yet)
    await websocket.send(json.dumps({
        "type": "connected", "version": "0.1.0",
    }))
```

Remove the old code that creates `WsEventHandler` and wires it to the master controller — that now happens inside `SessionManager.create_session()` / `load_session()`.

- [ ] **Step 3: Update session message handlers**

Replace the session-related message handlers inside the `async for raw_message in websocket:` loop:

```python
# ── Session management ──────────────────────────

elif msg_type == "create_session":
    project_path = msg.get("project_path", "")
    title = msg.get("title", "New Chat")
    session_id = store.create_session(project_path, title=title)
    await session_mgr.create_session(project_path, session_id, title)
    # Get the handler for initial debug events
    slot = session_mgr.get_active()
    handler = slot.handler
    # Send initial system info
    registry = slot.agent_manager.agents["master"].controller.registry
    await handler._send_debug(
        "[System]",
        f"Provider: {session_mgr._config.provider}  |  Model: {session_mgr._config.model or 'default'}\n"
        f"Tools: {', '.join(registry.get_tool_names())}\n"
        f"CWD: {session_mgr._config.cwd or Path.cwd()}",
        "#569cd6")
    await handler._send_debug("[System]", "MCP: no servers configured", "#94A3B8")
    await websocket.send(json.dumps({
        "type": "session_created",
        "session_id": session_id,
        "title": title,
    }, ensure_ascii=False))

elif msg_type == "load_session":
    project_path = msg.get("project_path", "")
    session_id = msg.get("session_id", "")
    messages = store.load_messages(project_path, session_id)
    meta = store.get_session_meta(project_path, session_id)
    debug_entries = store.load_debug_log(project_path, session_id)
    await session_mgr.load_session(project_path, session_id)
    slot = session_mgr.get_active()
    # Send system info to the new handler
    registry = slot.agent_manager.agents["master"].controller.registry
    await slot.handler._send_debug(
        "[System]",
        f"Provider: {session_mgr._config.provider}  |  Model: {session_mgr._config.model or 'default'}\n"
        f"Tools: {', '.join(registry.get_tool_names())}",
        "#569cd6")
    await websocket.send(json.dumps({
        "type": "session_loaded",
        "session_id": session_id,
        "messages": messages,
        "meta": meta,
        "debug_entries": debug_entries,
    }, ensure_ascii=False))

elif msg_type == "switch_session":
    session_id = msg.get("session_id", "")
    if session_id in session_mgr.slots and session_id != session_mgr.active_session_id:
        # Save current handler's debug state
        old_slot = session_mgr.get_active()
        if old_slot:
            old_slot.agent_manager.agents[old_slot.agent_manager.active_id].debug_events = \
                list(old_slot.handler._debug_entries)
        # Switch
        session_mgr.switch_session(session_id)
        new_slot = session_mgr.get_active()
        agent = new_slot.agent_manager.agents["master"].controller.agent
        debug_evts = new_slot.agent_manager.agents[
            new_slot.agent_manager.active_id].debug_events or []
        await websocket.send(json.dumps({
            "type": "active_session_switched",
            "session_id": session_id,
            "messages": [
                {"role": m.role, "content": m.content or ""}
                for m in agent.messages if not m.is_tool_result
            ],
            "debug_entries": debug_evts,
        }, ensure_ascii=False))

elif msg_type == "destroy_session":
    session_id = msg.get("session_id", "")
    await session_mgr.destroy_session(session_id)
    await websocket.send(json.dumps({
        "type": "session_destroyed",
        "session_id": session_id,
    }, ensure_ascii=False))
```

- [ ] **Step 4: Update non-session message handlers**

For `send_message`, `cancel`, `get_status`, etc., route through the active slot:

```python
if msg_type == "send_message":
    slot = session_mgr.get_active()
    if not slot:
        await websocket.send(json.dumps({
            "type": "error", "message": "No active session",
        }))
        continue
    manager = slot.agent_manager
    handler = slot.handler
    active_state = manager.get_active()
    if handler._controller is not active_state.controller:
        handler.set_controller(active_state.controller)
        active_state.controller.handler = handler
    handler._has_pending_tool_results = False
    if getattr(active_state.controller.agent, '_compacting', False):
        await handler._send_debug("[Blocked]", "正在压缩中，请稍候...", "#F59E0B")
        continue
    text = msg.get("text", "")
    queue = active_state.message_queue
    if queue:
        queue.enqueue(text, source="user")
    else:
        await active_state.controller.send_message(text)

elif msg_type == "cancel":
    slot = session_mgr.get_active()
    if slot:
        active_state = slot.agent_manager.get_active()
        await active_state.controller.cancel()
        await slot.handler._send_debug("[Stopped]", "用户中止了当前任务", "#EF4444")

elif msg_type == "clear_history":
    slot = session_mgr.get_active()
    if slot:
        slot.agent_manager.get_active().controller.clear_history()

elif msg_type == "compact":
    slot = session_mgr.get_active()
    if slot:
        agent = slot.agent_manager.get_active().controller.agent
        await slot.handler._do_compact(agent)
```

Similarly update `get_status`, `get_config`, `reconfigure`, `switch_agent`, `spawn_agent`, `kill_agent`, `mcp_stop`, `mcp_restart` to go through `session_mgr.get_active()`.

- [ ] **Step 5: Run all tests**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add agentcore/ws_server.py
git commit -m "feat: ws_server uses SessionManager — concurrent session routing"
```

---

### Task 5: Frontend — session status tracking and switching

**Files:**
- Modify: `ui/src/stores/session.ts`
- Modify: `ui/src/App.vue`

- [ ] **Step 1: Update session.ts**

Add `sessionStatuses` and `switchSession`:

```typescript
// Add to the store's state
const sessionStatuses = ref<Record<string, string>>({});

// Add new method
function switchSession(id: string) {
  if (id === currentSessionId.value) return;
  agentWs.send({ type: 'switch_session', session_id: id });
}

// Add method to update status
function setSessionStatus(sessionId: string, status: string) {
  sessionStatuses.value[sessionId] = status;
}

// Add method for active_session_switched
function setActiveSessionSwitched(data: { session_id: string; messages: any[]; debug_entries: any[] }) {
  currentSessionId.value = data.session_id;
}

// Export the new state and methods
return {
  // ... existing exports
  sessionStatuses,
  switchSession, setSessionStatus, setActiveSessionSwitched,
};
```

- [ ] **Step 2: Update App.vue event handlers**

Add handlers in the `onMounted` block:

```typescript
// Session status updates from background sessions
agentWs.on('session_status', (d: any) => {
  sessionStore.setSessionStatus(d.session_id, d.status);
});

// Active session switched
agentWs.on('active_session_switched', (d: any) => {
  sessionStore.setCurrentSession(d.session_id);
  chatStore.loadMessages(
    (d.messages || []).map((m: any) => ({ role: m.role, content: m.content }))
  );
  if (d.debug_entries) {
    debugStore.loadEvents(d.debug_entries);
  } else {
    debugStore.clear();
  }
});

// Session destroyed
agentWs.on('session_destroyed', (d: any) => {
  // Remove from sessions list
  const idx = sessionStore.sessions.findIndex(s => s.session_id === d.session_id);
  if (idx >= 0) sessionStore.sessions.splice(idx, 1);
});
```

Also update the existing `session_loaded` handler to not clear debug when it has entries (already done).

- [ ] **Step 3: Update SessionList switchSession to use new method**

In `SessionList.vue`, change `switchSession`:

```typescript
function switchSession(id: string) {
  if (id === sessionStore.currentSessionId) return;
  sessionStore.switchSession(id);
}
```

- [ ] **Step 4: Test in browser**

Run: `dev.bat`
Test: Create 2 sessions, send a message in one, switch to the other, verify messages don't mix.

- [ ] **Step 5: Commit**

```bash
git add ui/src/stores/session.ts ui/src/App.vue ui/src/components/SessionList.vue
git commit -m "feat: frontend session switching — concurrent session status tracking"
```

---

### Task 6: SessionList status dots

**Files:**
- Modify: `ui/src/components/SessionList.vue`

- [ ] **Step 1: Add status dot to session items**

Update the template in `SessionList.vue`:

```html
<div v-for="s in sessionStore.sessions" :key="s.session_id"
     :class="['session-item', { active: s.session_id === sessionStore.currentSessionId }]"
     @click="switchSession(s.session_id)">
  <div class="session-row">
    <span class="status-dot" :class="statusClass(s.session_id)"></span>
    <span class="session-title">{{ s.title }}</span>
  </div>
  <span class="session-meta">{{ s.msg_count }}条 · {{ formatTime(s.updated_at) }}</span>
</div>
```

Add helper and styles:

```typescript
function statusClass(sessionId: string): string {
  const status = sessionStore.sessionStatuses[sessionId] || 'idle';
  return `dot-${status}`;
}
```

Add CSS:

```css
.session-row { display: flex; align-items: center; gap: 6px; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot-running { background: #22C55E; animation: pulse 1.5s infinite; }
.dot-idle { background: #D1D5DB; }
.dot-error { background: #EF4444; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
```

- [ ] **Step 2: Test in browser**

Run: `dev.bat`
Test: Create session, send message, observe green dot. After completion, observe gray dot.

- [ ] **Step 3: Commit**

```bash
git add ui/src/components/SessionList.vue
git commit -m "feat: SessionList shows status dots — running/idle/error per session"
```

---

## Self-Review

**Spec coverage:**
- Section 1 (Rename) → Task 1 ✓
- Section 2 (Per-Controller Concurrency) → Verified: no lock change needed, confirmed in Task 2 ✓
- Section 3 (SessionSlot + SessionManager) → Task 2 ✓
- Section 4 (WsEventHandler active vs background) → Task 3 ✓
- Section 5 (WebSocket Protocol) → Tasks 4, 5 ✓
- Section 6 (Frontend) → Tasks 5, 6 ✓
- Section 7 (Persistence) → No change needed, covered by existing code ✓
- Section 8 (Lifecycle) → Covered by Tasks 2-5 ✓

**Placeholder scan:** No TBD/TODO/vague steps found.

**Type consistency:**
- `SessionSlot.session_id` is `str` throughout
- `SessionManager.active_session_id` is `str`
- `WsEventHandler._session_manager` is `SessionManager | None`
- `session_status` event has `session_id: str, status: str` — consistent everywhere
