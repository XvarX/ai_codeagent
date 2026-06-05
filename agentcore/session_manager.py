# agentcore/session_manager.py
"""SessionManager — manages concurrent sessions, each with its own AgentManager."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from agentcore.config import AgentConfig
from agentcore.data_dir import DataDir
from agentcore.session_store import SessionStore
from agentcore.subagent_manager import AgentManager

if TYPE_CHECKING:
    from websockets.asyncio.server import ServerConnection


@dataclass
class SessionSlot:
    """One active session: its own AgentManager + event handler."""
    session_id: str
    project_path: str
    agent_manager: AgentManager
    handler: object  # WsEventHandler, use object to avoid circular import
    store: SessionStore


class SessionManager:
    """Manages all active sessions. Created once in run_ws_server()."""

    def __init__(self, config: AgentConfig, store: SessionStore,
                 dd: DataDir, ws: "ServerConnection | None"):
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
        import asyncio

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
        import asyncio

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
