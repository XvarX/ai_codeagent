"""BroadcastRoomTool — LLM-controlled room broadcast for chat rooms."""

import sys
import time

from agentcore.tools.base import Tool, ToolContext


def _safe_print(msg: str) -> None:
    """Print that survives Windows GBK encoding for emoji / non-ASCII."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", "utf-8") or "utf-8"
        print(msg.encode(enc, errors="replace").decode(enc), flush=True)


def _resolve_to(raw: str, room, mgr) -> str:
    """Validate and normalize the `to` target agent/user.

    Returns the member's display name if valid, empty string otherwise.
    """
    raw = raw.strip()
    if raw == "用户":
        return raw
    # Try id exact match first, then name fuzzy match
    for aid in room.agent_ids:
        st = mgr.agents.get(aid)
        if not st:
            continue
        if raw == aid or raw == st.name:
            return st.name
    return ""


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
            "向聊天室发送消息，让房间内其他成员看到你的回复。"
            "收到用户从聊天室发送的消息时必须调用此工具回复，直接在对话中回复用户看不到；"
            "收到其他Agent发言中有明显错误或关键遗漏时调用纠正/补充；"
            "用户明确要求你回应时调用。"
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
                "to": {
                    "type": "string",
                    "description": "回复对象。填 '用户' 或成员名/id。留空从最近一条用户消息的 From 字段自动推断。",
                },
            },
            "required": ["message"],
        }
        self._manager = manager
        self._from_id = from_agent_id

    def is_read_only(self) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> str:
        message = input["message"]
        room_id = input.get("room_id", "")

        # ── Resolve agent ──
        mgr = self._manager
        agent_state = mgr.agents.get(self._from_id)
        if not agent_state or not agent_state.controller:
            self.suppress_reply = False
            return f"Agent '{self._from_id}' not found."

        agent = agent_state.controller.agent

        # ── Guard: SendMessage 私聊触发的处理禁止调用 BroadcastRoom ──
        if getattr(agent, '_current_source', '') == 'agent':
            self.suppress_reply = False
            return "当前正在处理其他 Agent 的私聊请求，禁止调用 BroadcastRoom。如需回复请使用 SendMessage 私聊。"

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

        # ── Resolve target (to) ──
        from_name = agent_state.name or "unknown"
        reply_to = input.get("to", "") or input.get("reply_to", "") or ""

        # A: LLM-specified `to` — validate and normalize
        if reply_to:
            resolved = _resolve_to(reply_to, room, mgr)
            if resolved:
                reply_to = resolved
            else:
                reply_to = ""  # invalid → fallback to auto-detect

        # B: Auto-detect from last user message
        if not reply_to:
            for m in reversed(agent.messages):
                if m.role == "user" and m.content:
                    import re
                    fm = re.search(r"\|\s*From:\s*([^|\]]+)", m.content)
                    if fm:
                        raw = fm.group(1).strip()
                        reply_to = re.sub(r"\s*\(id:[^)]*\)\s*$", "", raw).strip()
                    break
            if not reply_to:
                reply_to = "用户"

        # ── Format and broadcast ──
        formatted = (
            f"[Room: {room.name} | From: {from_name}"
            f" | To: {reply_to}]\n{message}"
        )

        now = time.time()
        agent._last_broadcast_ts = getattr(agent, '_last_broadcast_ts', None) or {}
        agent._last_broadcast_ts[room_id] = now

        target_count = 0
        relay_meta = {
            "room_id": room_id,
            "room_name": room.name,
            "from_name": from_name,
            "from_id": self._from_id,
            "text": message,
            "reply_to": reply_to,
            "ts": now,
        }
        for aid in room.agent_ids:
            if aid == self._from_id:
                continue
            st = mgr.agents.get(aid)
            if st and st.message_queue:
                st.message_queue.enqueue(
                    formatted, source="room", room_id=room_id, relay=True,
                    relay_meta=relay_meta,
                )
                target_count += 1

        self.suppress_reply = True  # success → suppress LLM follow-up

        # Push to frontend via THIS agent's own handler. Only the active
        # agent's handler (WsEventHandler) has _send — non-active agents
        # use _AgentHandler which doesn't, so their broadcasts reach the
        # frontend only when the active agent dequeues them in consumer_loop.
        ws_handler = agent_state.controller.handler

        # Push to chatroom panel immediately via manager's global ws_handler.
        # This bypasses the active agent's message queue so the chatroom panel
        # shows messages from non-active agents without waiting for the active
        # agent to finish its current turn.
        mgr_ws = mgr.ws_handler
        if mgr_ws and hasattr(mgr_ws, "_send"):
            try:
                await mgr_ws._send({
                    "type": "room_chat",
                    "room_id": room_id,
                    "room_name": room.name,
                    "from_name": from_name,
                    "from_id": self._from_id,
                    "text": message,
                    "reply_to": reply_to,
                })
            except Exception:
                pass

        if ws_handler and hasattr(ws_handler, "_send"):
            try:
                await ws_handler._send({
                    "type": "room_relay",
                    "room_id": room_id,
                    "room_name": room.name,
                    "from_name": from_name,
                    "from_id": self._from_id,
                    "text": message,
                    "reply_to": reply_to,
                })
            except Exception:
                pass

        _safe_print(
            f"[BroadcastRoom] {from_name} ({self._from_id}) "
            f"broadcast to {target_count} members in '{room.name}'"
        )
        return f"已广播到房间「{room.name}」的 {target_count} 个成员。"
