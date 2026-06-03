"""AgentTool — lets LLM spawn subagents."""

from agentcore.tools.base import Tool, ToolContext
from agentcore.agent_definitions import resolve_agent, list_all_agents


class AgentTool(Tool):
    """Spawn a subagent to handle a specific task."""

    def __init__(self, manager, user_agents: dict | None = None):
        self.name = "Agent"
        self.description = (
            "Launch a new agent to handle complex, multi-step tasks. "
            "Each agent type has specific capabilities and tools available to it. "
            "Agents can optionally stay alive after completing their task (keep_alive), "
            "allowing you to send them further messages via SendMessage."
        )
        self.parameters = {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "A short (3-5 word) description of the task",
                },
                "prompt": {
                    "type": "string",
                    "description": "The task for the agent to perform",
                },
                "subagent_type": {
                    "type": "string",
                    "description": (
                        "The type of specialized agent to use for this task. "
                        "Available: explore (read-only code search), "
                        "plan (architecture design), "
                        "general-purpose (any task)"
                    ),
                },
                "run_in_background": {
                    "type": "boolean",
                    "description": "Set to true to run this agent in the background.",
                },
                "keep_alive": {
                    "type": "boolean",
                    "description": (
                        "Set to true to keep the agent alive after it completes its task. "
                        "The agent can then receive follow-up messages via SendMessage. "
                        "If false or omitted, the agent is cleaned up after completion."
                    ),
                },
                "name": {
                    "type": "string",
                    "description": "Name for the spawned agent. Required if keep_alive is true. Makes it addressable via SendMessage.",
                },
            },
            "required": ["description", "prompt"],
        }
        self._manager = manager
        self._user_agents = user_agents or {}

    def is_read_only(self) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> str:
        description = input.get("description", "")
        prompt = input.get("prompt", "")
        subagent_type = input.get("subagent_type", "general-purpose")
        background = input.get("run_in_background", False)
        keep_alive = input.get("keep_alive", False)
        name = input.get("name", "")

        definition = resolve_agent(subagent_type, self._user_agents)
        if definition is None:
            available = ["explore", "plan", "general-purpose"]
            available.extend(self._user_agents.keys())
            return f"Unknown agent type: {subagent_type}\nAvailable: {', '.join(available)}"

        if keep_alive and not name:
            return "Error: name is required when keep_alive is true."

        try:
            agent_id = await self._manager.spawn(
                definition=definition,
                prompt=prompt,
                background=background,
                keep_alive=keep_alive,
                name=name,
            )
            state = self._manager.agents[agent_id]

            if background:
                return (
                    f"Agent spawned in background.\n"
                    f"Name: {state.name}\n"
                    f"ID: {agent_id}\n"
                    f"Type: {definition.name}\n"
                    f"Status: running"
                )
            else:
                return (
                    f"Agent completed.\n"
                    f"Name: {state.name}\n"
                    f"Status: {state.status}\n\n"
                    f"{state.result}"
                )
        except Exception as e:
            return f"Agent spawn failed: {e}"
