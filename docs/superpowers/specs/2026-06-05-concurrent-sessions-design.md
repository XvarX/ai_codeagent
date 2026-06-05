# Concurrent Sessions Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Multiple sessions run concurrently with independent agent trees, each session's agents (master + subagents) execute in parallel via asyncio coroutines.

**Architecture:** New `SessionManager` manages multiple `SessionSlot` instances. Each slot owns an `AgentManager` (renamed from SubagentManager) with its own master agent and subagents. Per-controller locks replace the global lock to enable true coroutine concurrency. Only the active session streams events to the frontend; background sessions persist events to disk.

**Tech Stack:** Python asyncio, WebSocket, Vue 3 + Pinia

---

## 1. Rename: SubagentManager → AgentManager

`SubagentManager` already manages master + subagents. Rename to `AgentManager` for clarity.

**Scope:**
- Rename class `SubagentManager` → `AgentManager`
- Rename all references: imports, variable names, docstrings, error messages
- File stays `agentcore/subagent_manager.py` (internal module naming is less important than class naming)
- Update `_SubagentHandler` → `_AgentHandler`
- Update log prefix `[SubagentMgr]` → `[AgentMgr]`

**Files touched:** `subagent_manager.py`, `ws_server.py`, `controller.py`, `agent.py`, any files importing SubagentManager

## 2. Per-Controller Concurrency

**Current problem:** `AgentController._agent_lock` is per-controller, but `spawn()` uses `async with controller._agent_lock` which serializes calls to the same controller. Different controllers can already run concurrently.

**What needs to change:**
- The lock is already per-controller — each `AgentManager` instance creates its own controllers with their own locks
- Since each session gets its own `AgentManager`, sessions are already naturally isolated
- **No lock change needed** — the existing per-controller lock is correct

**Verification needed:**
- Confirm `_agent_lock` is an instance variable (not class variable) in `AgentController.__init__`
- Confirm each `AgentManager.spawn()` creates a new controller (it does — line 417)

## 3. SessionSlot + SessionManager

### SessionSlot

```python
class SessionSlot:
    """One active session: its own AgentManager + event handler."""
    session_id: str
    project_path: str
    agent_manager: AgentManager
    handler: WsEventHandler
    store: SessionStore
```

### SessionManager

```python
class SessionManager:
    """Manages all active sessions. Created once in run_ws_server()."""

    def __init__(self, config, store, dd):
        self.slots: dict[str, SessionSlot] = {}
        self.active_session_id: str = ""
        self._config = config
        self._store = store
        self._dd = dd
        self._ws: ServerConnection  # shared WebSocket

    async def create_session(self, project_path, title) -> str:
        """Create new slot with its own AgentManager, bind store, return session_id."""

    async def load_session(self, project_path, session_id):
        """Create slot, restore messages + debug entries from disk."""

    async def destroy_session(self, session_id):
        """Kill all agents in slot, remove slot."""

    async def switch_session(self, session_id):
        """Change active session. Active handler streams to frontend."""

    def get_active(self) -> SessionSlot | None:
        """Get the currently viewed session slot."""

    async def send_message(self, session_id, text):
        """Route user message to the specified session's master agent.
        Frontend always sends to the active session. Background sessions
        receive messages only through their internal agent message queues
        (e.g., subagent SendMessage tool)."""

    def handle_ws_message(self, msg):
        """Route any WebSocket message to the active session's AgentManager."""
```

### Key behavior:
- `create_session` creates a `SessionSlot` with a fresh `AgentManager(config)` and `WsEventHandler(ws, controller)`
- `load_session` creates slot + restores messages via `agent.restore_messages()`
- Only the active session's `WsEventHandler` sends events to the frontend
- Background session handlers persist to `debug_log.json` only
- `switch_session` updates `active_session_id` and tells the frontend to reload

## 4. WsEventHandler: Active vs Background

Each `WsEventHandler` needs to know if it's the active one.

**Change:** Add `is_active` property check before sending WebSocket events.

```python
async def _send(self, data: dict):
    """Send to frontend only if this handler's session is active."""
    if self._session_id == self._session_manager.active_session_id:
        await self._ws.send(json.dumps(data, ensure_ascii=False))
    # Always persist debug events (handled in _send_debug)
```

**New attribute:** `self._session_manager: SessionManager` — replaces the need for direct WebSocket send.

## 5. WebSocket Protocol Changes

### New messages (frontend → backend):

| Type | Fields | Description |
|------|--------|-------------|
| `switch_session` | `session_id` | Switch active session view |
| `destroy_session` | `session_id` | Kill session and clean up |

### Existing messages (modified):

| Type | Change |
|------|--------|
| `create_session` | Now creates SessionSlot instead of just touching Agent |
| `load_session` | Now creates SessionSlot + restores state |
| `send_message` (chat) | Routed to active session's master agent |

### New events (backend → frontend):

| Type | Fields | Description |
|------|--------|-------------|
| `session_status` | `session_id`, `status` | Background session status change (running/idle/completed/error) |
| `active_session_switched` | `session_id`, `messages`, `debug_entries` | Full state dump after switching |

### Modified events:

| Type | Change |
|------|--------|
| All existing events | Now include `session_id` field so frontend can filter |

## 6. Frontend Changes

### session.ts store:

- `currentSessionId` used as active view
- `sessionStatuses: Record<string, string>` — tracks status per session
- `switchSession(id)` sends `switch_session` message
- Handle `session_status` events to update status badges

### App.vue:

- `session_loaded` / `active_session_switched` restores chat + debug state
- `session_status` updates session list badges (running indicator)

### SessionList.vue:

- Show status dot per session using **aggregate status** from the session's AgentManager:
  - Any agent running → **running** (green)
  - All agents idle/completed → **idle** (gray)
  - Any agent failed with nothing running → **error** (red)
- Show unread indicator when background session has new activity

## 7. Persistence

Each session already has its own `messages.json`, `debug_log.json`, `llm_log.json` under `.ai-code-agent/store/projects/{hash}/sessions/{uuid}/`.

No change to persistence format. Background sessions persist the same way.

## 8. Lifecycle

```
User opens project → load_project → list sessions
User clicks "+" → create_session → SessionSlot created, master agent ready
User types message → send_message → routed to slot's master agent
  → Agent may spawn subagents within same AgentManager
  → All events persisted to disk, only active session streams to frontend
User clicks another session → switch_session
  → Active slot switches
  → Frontend receives active_session_switched with full state
  → Old session continues running in background
User closes session → destroy_session
  → All agents killed, slot removed
  → Session data remains on disk
```

## 9. Resource Considerations

- No hard limit on concurrent sessions
- Each session = 1 AgentManager with its own controller(s)
- API rate limits naturally bound concurrency
- Background sessions don't stream to WebSocket (saves bandwidth)
- Consider adding a configurable max_sessions (default: unlimited) for safety

## 10. Files to Modify

| File | Change |
|------|--------|
| `agentcore/subagent_manager.py` | Rename class → AgentManager, rename handler, log prefix |
| `agentcore/session_manager.py` | **NEW** — SessionSlot + SessionManager |
| `agentcore/ws_server.py` | Use SessionManager instead of SubagentManager directly; route messages to active slot |
| `agentcore/controller.py` | No change needed (per-controller lock already correct) |
| `ui/src/stores/session.ts` | Add sessionStatuses, switchSession with full state restore |
| `ui/src/App.vue` | Handle session_status, active_session_switched events |
| `ui/src/components/SessionList.vue` | Show status dots, unread badges |
