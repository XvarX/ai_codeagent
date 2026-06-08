# agentcore/session_manager.py
"""SessionManager — manages concurrent sessions, each with its own AgentManager."""

from __future__ import annotations

import json
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

        # Wire subagent persistence — called after every AgentManager.spawn
        store_ref = self._store
        proj_ref = project_path
        sess_ref = session_id
        async def _on_spawn(agent_id: str, state):
            sub_sess = f"{sess_ref}/subagents/{agent_id}"
            state.controller.agent.bind_session(store_ref, proj_ref, sub_sess)
            store_ref.save_subagent_meta(proj_ref, sess_ref, agent_id, {
                "id": agent_id, "name": state.name,
                "definition": {
                    "name": state.definition.name,
                    "description": state.definition.description,
                    "agent_type": state.definition.agent_type,
                    "system_prompt": state.definition.system_prompt,
                    "tools": state.definition.tools,
                    "source": state.definition.source,
                },
                "status": state.status, "keep_alive": state.keep_alive,
            })
        mgr.on_spawn = _on_spawn

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
        """Create slot and restore messages + debug entries from disk.
        If slot already exists, just switch to it without rebuilding."""
        if session_id in self.slots:
            self.active_session_id = session_id
            return

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

        # Wire subagent persistence — called after every AgentManager.spawn
        store_ref = self._store
        proj_ref = project_path
        sess_ref = session_id
        async def _on_spawn(agent_id: str, state):
            sub_sess = f"{sess_ref}/subagents/{agent_id}"
            state.controller.agent.bind_session(store_ref, proj_ref, sub_sess)
            store_ref.save_subagent_meta(proj_ref, sess_ref, agent_id, {
                "id": agent_id, "name": state.name,
                "definition": {
                    "name": state.definition.name,
                    "description": state.definition.description,
                    "agent_type": state.definition.agent_type,
                    "system_prompt": state.definition.system_prompt,
                    "tools": state.definition.tools,
                    "source": state.definition.source,
                },
                "status": state.status, "keep_alive": state.keep_alive,
            })
        mgr.on_spawn = _on_spawn

        slot = SessionSlot(
            session_id=session_id,
            project_path=project_path,
            agent_manager=mgr,
            handler=handler,
            store=self._store,
        )
        self.slots[session_id] = slot
        self.active_session_id = session_id

        # Restore persisted subagents
        await self._restore_subagents(slot)

    async def _restore_subagents(self, slot: SessionSlot):
        """Recreate subagents from persisted metadata."""
        from agentcore.subagent_manager import _AgentHandler, SubagentState
        from agentcore.agent_definitions import AgentDefinition
        from agentcore.agent_message_queue import AgentMessageQueue
        from agentcore.controller import AgentController

        subagents = self._store.list_subagents(slot.project_path, slot.session_id)
        for meta in subagents:
            sub_id = meta["id"]
            defn_data = meta.get("definition", {})
            definition = AgentDefinition(
                name=defn_data.get("name", meta["name"]),
                description=defn_data.get("description", ""),
                agent_type=defn_data.get("agent_type", "user"),
                system_prompt=defn_data.get("system_prompt", ""),
                tools=defn_data.get("tools"),
                source=defn_data.get("source", "user"),
            )

            handler = _AgentHandler(slot.agent_manager, sub_id)
            controller = AgentController(self._config, handler)
            queue = AgentMessageQueue(controller)
            controller.agent._agent_manager = slot.agent_manager
            controller.agent._agent_id = sub_id

            # Bind session store for auto message persistence
            sub_session_id = f"{slot.session_id}/subagents/{sub_id}"
            controller.agent.bind_session(
                self._store, slot.project_path, sub_session_id)

            # Restore subagent messages
            msgs_path = self._dd.session_dir(
                slot.project_path, slot.session_id) / "subagents" / sub_id / "messages.json"
            if msgs_path.exists():
                sub_msgs = json.loads(msgs_path.read_text(encoding="utf-8"))
                if sub_msgs:
                    controller.agent.restore_messages(sub_msgs)

            state = SubagentState(
                id=sub_id,
                name=meta["name"],
                definition=definition,
                controller=controller,
                message_queue=queue,
                status=meta.get("status", "completed"),
                result=meta.get("result", ""),
                error=meta.get("error", ""),
                est_tokens=meta.get("est_tokens", 0),
                keep_alive=meta.get("keep_alive", False),
            )
            # Wire debug events from disk
            debug_path = self._dd.session_dir(
                slot.project_path, slot.session_id) / "subagents" / sub_id / "debug_log.json"
            if debug_path.exists():
                state.debug_events = json.loads(debug_path.read_text(encoding="utf-8"))
            else:
                state.debug_events = []

            # Register SendMessage tool
            from agentcore.tools.send_message_tool import SendMessageTool
            send_tool = SendMessageTool(slot.agent_manager, sub_id)
            controller.registry.register(send_tool)

            slot.agent_manager.agents[sub_id] = state

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
