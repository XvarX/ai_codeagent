"""SendMessageTool — inter-agent messaging."""

from tools.base import Tool, ToolContext


class SendMessageTool(Tool):
    """Send a message to another agent via its inbox."""

    def __init__(self, manager, from_agent_id: str):
        self.name = "SendMessage"
        self.description = (
            "Send a message to another agent. "
            "Use to coordinate between agents or delegate subtasks."
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
        try:
            await self._manager.send_message_to_agent(self._from_id, to, message)
            return f"Message sent to '{to}'."
        except ValueError as e:
            return str(e)
