"""SubagentManager — manages multiple AgentController instances."""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from config import AgentConfig
from controller import AgentController, EventHandler, _build_registry, _build_provider
from agent_definitions import AgentDefinition


@dataclass
class SubagentState:
    """Runtime state for one subagent."""
    id: str
    name: str
    definition: AgentDefinition
    controller: AgentController
    inbox: asyncio.Queue
    status: str = "pending"
    result: str = ""
    error: str = ""
    background_task: asyncio.Task | None = None
    turn_count: int = 0
    est_tokens: int = 0
    debug_events: list = field(default_factory=list)  # captured debug entries


def _build_provider_for_agent(config: AgentConfig, definition: AgentDefinition):
    """Build a provider for a specific agent definition.

    Uses agent definition's provider override, or falls back to default config.
    """
    if definition.provider:
        provider_name = definition.provider.lower()
        # Check config.yaml for provider type
        import yaml
        config_path = Path("config.yaml")
        if not config_path.exists():
            return _build_provider(config)

        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        provider_type = cfg.get("provider_types", {}).get(provider_name, "").lower()
        api_key = cfg.get("api_keys", {}).get(provider_name, config.api_key or "")
        base_url = cfg.get("base_urls", {}).get(provider_name, config.base_url or "")
        model = definition.model or cfg.get("models", {}).get(provider_name, config.model or "")

        if provider_type == "anthropic" or (not provider_type and provider_name == "anthropic"):
            from providers.anthropic import AnthropicProvider
            return AnthropicProvider(model=model, api_key=api_key, base_url=base_url)
        else:
            from providers.openai_compat import OpenAICompatProvider
            return OpenAICompatProvider(
                provider=provider_name, model=model,
                api_key=api_key, base_url=base_url,
            )

    return _build_provider(config)


def _build_tool_registry_for_agent(config: AgentConfig, definition: AgentDefinition, parent_registry=None):
    """Build a ToolRegistry for an agent, applying tool restrictions.

    If definition.tools is None, all tools are inherited.
    If definition.tools is a list, only those tools are included (minus disallowed).
    """
    base_registry, skills_text = _build_registry(config.cwd)

    if definition.tools is None:
        return base_registry, skills_text

    from tools.registry import ToolRegistry
    filtered = ToolRegistry()
    allowed = set(definition.tools)
    disallowed = set(definition.disallowed_tools or [])
    for tool in base_registry.list_all():
        if tool.name in disallowed:
            continue
        if tool.name in allowed:
            filtered.register(tool)
    return filtered, skills_text


class _SubagentHandler(EventHandler):
    """EventHandler that captures subagent events for status updates and debug."""

    def __init__(self, manager: "SubagentManager", agent_id: str):
        super().__init__()
        self.manager = manager
        self.agent_id = agent_id

    def _log(self, prefix: str, message: str, color: str = "#94A3B8"):
        state = self.manager.agents.get(self.agent_id)
        if state:
            state.debug_events.append({
                "prefix": prefix, "message": message, "color": color,
            })

    async def on_thinking(self):
        self._log("[Thinking]", "Agent thinking...", "#6366F1")

    async def on_tool_use(self, name: str, input_dict: dict, tool_use_id: str = ""):
        preview = ", ".join(f"{k}={str(v)[:50]}" for k, v in input_dict.items())
        self._log(f"[Tool] {name}", preview, "#22C55E")

    async def on_tool_result(self, name: str, result: str, is_error: bool, duration_ms: float = 0, tool_use_id: str = ""):
        preview = result[:200].replace("\n", " ")
        color = "#EF4444" if is_error else "#8B5CF6"
        self._log(f"[Result] {name}", preview, color)

    async def on_response_done(self, raw: dict):
        usage = raw.get("usage", {})
        tokens = usage.get("total_tokens") or usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        self._log("[Response]", f"Done  |  ~{tokens} tokens", "#3B82F6")

    async def on_error(self, message: str):
        state = self.manager.agents.get(self.agent_id)
        if state:
            state.error = message
        self._log("[Error]", message, "#EF4444")

    async def on_done(self, final_text: str):
        state = self.manager.agents.get(self.agent_id)
        if state:
            state.result = final_text
        self._log("[Done]", final_text[:200], "#6366F1")


class SubagentManager:
    """Manages the lifecycle of all agents (master + subagents)."""

    def __init__(self, config: AgentConfig, master_handler: EventHandler,
                 user_agents: dict[str, AgentDefinition] | None = None):
        self.config = config
        self.user_agents = user_agents or {}
        self.master_handler = master_handler
        self.agents: dict[str, SubagentState] = {}
        self.active_id: str = "master"
        self.on_change = None  # set by UI to refresh sidebar

        self._create_master()

    def _create_master(self):
        """Create the master agent controller."""
        controller = AgentController(self.config, self.master_handler)
        state = SubagentState(
            id="master",
            name="Master",
            definition=AgentDefinition(
                name="Master", description="Main agent",
                agent_type="built-in", system_prompt="",
                tools=None, source="built-in",
            ),
            controller=controller,
            inbox=asyncio.Queue(),
            status="running",
        )
        self.agents["master"] = state

    async def spawn(self, definition: AgentDefinition, prompt: str,
                    background: bool = False, name: str = "") -> str:
        """Spawn a new subagent. Returns agent_id."""
        import time
        agent_id = f"{definition.name.lower()}-{int(time.time() * 1000)}"

        provider = _build_provider_for_agent(self.config, definition)
        registry, skills_text = _build_tool_registry_for_agent(self.config, definition)

        handler = _SubagentHandler(self, agent_id)
        controller = AgentController(self.config, handler)
        controller.provider = provider
        controller.registry = registry
        controller.agent.provider = provider
        controller.agent.registry = registry
        controller.agent.skills_text = skills_text

        # Register SendMessage tool on this agent
        from tools.send_message_tool import SendMessageTool
        send_tool = SendMessageTool(self, agent_id)
        controller.registry.register(send_tool)

        state = SubagentState(
            id=agent_id,
            name=name or definition.name,
            definition=definition,
            controller=controller,
            inbox=asyncio.Queue(),
            status="running" if background else "pending",
        )
        self.agents[agent_id] = state

        if background:
            state.background_task = asyncio.create_task(
                self._run_background(agent_id, prompt)
            )
        else:
            state.status = "running"
            try:
                await controller.send_message(prompt)
                assistant_msgs = [
                    m.content for m in controller.agent.messages
                    if m.role == "assistant" and m.content
                ]
                state.result = "\n".join(assistant_msgs) if assistant_msgs else "(no response)"
                state.status = "completed"
            except Exception as e:
                state.error = str(e)
                state.status = "failed"

        self._update_est_tokens(agent_id)
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                pass
        return agent_id

    async def _run_background(self, agent_id: str, prompt: str):
        """Run a subagent in the background."""
        state = self.agents[agent_id]
        try:
            state.status = "running"
            await state.controller.send_message(prompt)
            assistant_msgs = [
                m.content for m in state.controller.agent.messages
                if m.role == "assistant" and m.content
            ]
            state.result = "\n".join(assistant_msgs) if assistant_msgs else "(no response)"
            state.status = "completed"
        except asyncio.CancelledError:
            state.status = "killed"
        except Exception as e:
            state.error = str(e)
            state.status = "failed"
        finally:
            state.background_task = None
            self._update_est_tokens(agent_id)
            # Notify master handler so UI can refresh
            try:
                await self.master_handler.on_subagent_done(
                    agent_id, state.status, state.result)
            except Exception:
                pass
            # Fire on_change callback if set
            if self.on_change:
                try:
                    self.on_change()
                except Exception:
                    pass

    def _update_est_tokens(self, agent_id: str):
        state = self.agents.get(agent_id)
        if state:
            state.est_tokens = state.controller.agent.est_tokens()

    async def kill(self, agent_id: str):
        """Kill a running subagent."""
        if agent_id == "master":
            return
        state = self.agents.get(agent_id)
        if not state:
            return
        await state.controller.cancel()
        if state.background_task and not state.background_task.done():
            state.background_task.cancel()
        state.status = "killed"

    def switch(self, agent_id: str) -> SubagentState | None:
        """Switch the active agent view."""
        if agent_id not in self.agents:
            return None
        self.active_id = agent_id
        return self.agents[agent_id]

    def get_active(self) -> SubagentState:
        """Get current active agent state."""
        return self.agents[self.active_id]

    async def send_message_to_agent(self, from_id: str, to_name_or_id: str, message: str):
        """Send a message from one agent to another via inbox."""
        target = None
        for aid, st in self.agents.items():
            if aid == to_name_or_id or st.name.lower() == to_name_or_id.lower():
                target = aid
                break
        if target is None:
            raise ValueError(f"Agent '{to_name_or_id}' not found")

        from_state = self.agents.get(from_id)
        from_name = from_state.name if from_state else "unknown"
        await self.agents[target].inbox.put({
            "from": from_id,
            "from_name": from_name,
            "message": message,
        })

    def list_subagents(self) -> list[SubagentState]:
        """Return all subagents (excluding master)."""
        return [s for aid, s in self.agents.items() if aid != "master"]
