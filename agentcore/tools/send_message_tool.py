"""SendMessageTool — inter-agent messaging."""

from agentcore.tools.base import Tool, ToolContext


class SendMessageTool(Tool):
    """Send a message to another agent via its inbox."""

    def __init__(self, manager, from_agent_id: str):
        self.name = "SendMessage"
        self.description = (
            "Send a message to another agent by name. "
            "Use to share information, coordinate, delegate tasks, or send follow-up instructions."
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
        print(f"[SendMessage] {self._from_id} -> {to}: {message[:100]}", flush=True)
        try:
            await self._manager.send_message_to_agent(self._from_id, to, message)
            print(f"[SendMessage] delivered to {to}", flush=True)
            return f"Message sent to '{to}'."
        except ValueError as e:
            print(f"[SendMessage] failed: {e}", flush=True)
            return str(e)
