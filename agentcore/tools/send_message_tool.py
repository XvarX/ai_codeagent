"""SendMessageTool — inter-agent messaging."""

import sys

from agentcore.tools.base import Tool, ToolContext


def _safe_print(msg: str) -> None:
    """Print that survives Windows GBK encoding for emoji / non-ASCII."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", "utf-8") or "utf-8"
        print(msg.encode(enc, errors="replace").decode(enc), flush=True)


class SendMessageTool(Tool):
    """Send a message to another agent via its inbox."""

    def __init__(self, manager, from_agent_id: str):
        self.name = "SendMessage"
        self.description = (
            "向其他 Agent 发送私聊消息。用于分享信息、协调分工、委派任务或发送跟进指令。"
            "注意：如果目标 Agent 与你在同一个聊天室中，且话题是聊天室内的公开讨论，"
            "应使用 BroadcastRoom 向房间广播而非私聊，让所有成员都能看到。"
        )
        self.parameters = {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Target agent name or ID",
                },
                "message": {
                    "type": "string",
                    "description": "Message content",
                },
            },
            "required": ["to", "message"],
        }
        self._manager = manager
        self._from_id = from_agent_id

    def is_read_only(self) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> str:
        to = input["to"]
        message = input["message"]
        _safe_print(f"[SendMessage] {self._from_id} -> {to}: {message[:100]}")
        try:
            await self._manager.send_message_to_agent(self._from_id, to, message)
            _safe_print(f"[SendMessage] delivered to {to}")
            return f"Message sent to '{to}'."
        except ValueError as e:
            _safe_print(f"[SendMessage] failed: {e}")
            return str(e)
