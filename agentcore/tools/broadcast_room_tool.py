"""BroadcastRoomTool — LLM-controlled room broadcast for chat rooms."""

import sys

from agentcore.tools.base import Tool, ToolContext


def _safe_print(msg: str) -> None:
    """Print that survives Windows GBK encoding for emoji / non-ASCII."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", "utf-8") or "utf-8"
        print(msg.encode(enc, errors="replace").decode(enc), flush=True)


class BroadcastRoomTool(Tool):
    """Broadcast a message to other agents in your chat room.

    The LLM decides when to call this tool — there is no automatic
    re-broadcast.  suppress_reply=True so a successful broadcast does not
    trigger another LLM round (saves tokens).
    """

    suppress_reply = True

    def __init__(self, manager, from_agent_id: str):
        self.name = "BroadcastRoom"
        self.description = (
            "将你的回复广播给房间其他成员。收到用户消息时优先调用此工具，"
            "让房间内所有成员看到你的回复。"
            "注意：不要在每次收到其他 Agent 的中继消息时都调用此工具。"
            "仅在以下情况主动调用：需要纠正错误信息、补充关键遗漏、"
            "或用户明确要求你回应。如果讨论已达成共识或你只是认可对方的观点，"
            "不要调用。可通过 room_id 参数指定目标房间。"
        )
        self.parameters = {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "要广播给房间其他成员的消息内容",
                },
                "room_id": {
                    "type": "string",
                    "description": "目标房间 ID（多房间时必须指定，单房间可省略）",
                },
            },
            "required": ["message"],
        }
        self._manager = manager
        self._from_id = from_agent_id
        self._has_broadcast: bool = False

    def is_read_only(self) -> bool:
        return True

    def reset_broadcast_flag(self) -> None:
        """Reset the per-turn broadcast flag. Called before each room message."""
        self._has_broadcast = False

    async def call(self, input: dict, context: ToolContext) -> str:
        # ── Guard: one broadcast per turn ──
        if self._has_broadcast:
            # Don't suppress reply on error — let LLM see the message
            self.suppress_reply = False
            return "本轮已广播过一次，不可重复调用 BroadcastRoom。"

        message = input["message"]
        room_id = input.get("room_id", "")

        # ── Resolve room ──
        mgr = self._manager
        agent_state = mgr.agents.get(self._from_id)
        if not agent_state or not agent_state.controller:
            self.suppress_reply = False
            return f"Agent '{self._from_id}' not found."

        agent = agent_state.controller.agent

        # Determine target room
        if not room_id:
            room_id = getattr(agent, "_current_room_id", "") or ""

        if not room_id:
            self.suppress_reply = False
            return "未指定 room_id 且当前不在任何房间上下文中。"

        if not hasattr(mgr, "_rooms") or not mgr._rooms:
            self.suppress_reply = False
            return "当前没有活跃的聊天室。"

        room = mgr._rooms.get(room_id)
        if not room:
            self.suppress_reply = False
            return f"房间 '{room_id}' 不存在。"

        if self._from_id not in room.agent_ids:
            self.suppress_reply = False
            return f"你不在这个房间中（{room.name}）。"

        # ── Format and broadcast ──
        from_name = getattr(agent, "_agent_name", "") or "unknown"
        formatted = (
            f"[Room: {room.name} | From: {from_name} (id:{self._from_id})]\n{message}"
        )

        target_count = 0
        for aid in room.agent_ids:
            if aid == self._from_id:
                continue
            st = mgr.agents.get(aid)
            if st and st.message_queue:
                st.message_queue.enqueue(
                    formatted, source="room", room_id=room_id, relay=True,
                )
                target_count += 1

        # ── Notify frontend via room_relay event ──
        # Use mgr.ws_handler (always WsEventHandler) instead of a specific
        # agent's controller.handler which may be _AgentHandler after switch.
        ws_handler = mgr.ws_handler
        if ws_handler and hasattr(ws_handler, "_send"):
            try:
                await ws_handler._send({
                    "type": "room_relay",
                    "room_id": room_id,
                    "room_name": room.name,
                    "from_name": from_name,
                    "from_id": self._from_id,
                    "text": message,
                    "reply_to": "",
                })
            except Exception:
                pass

        self._has_broadcast = True
        self.suppress_reply = True  # success → suppress LLM follow-up

        _safe_print(
            f"[BroadcastRoom] {from_name} ({self._from_id}) "
            f"broadcast to {target_count} members in '{room.name}'"
        )
        return f"已广播到房间「{room.name}」的 {target_count} 个成员。"
