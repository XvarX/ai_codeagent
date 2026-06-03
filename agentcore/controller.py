"""AgentController — framework-agnostic Agent lifecycle wrapper."""

import asyncio

from config import AgentConfig
from tools.registry import ToolRegistry
from tools.bash import BashTool
from tools.file_read import FileReadTool
from tools.file_edit import FileEditTool
from tools.file_write import FileWriteTool
from tools.glob import GlobTool
from tools.grep import GrepTool
from providers.anthropic import AnthropicProvider
from providers.openai_compat import OpenAICompatProvider
from agent import Agent
from events import (
    ThinkingEvent, TextDeltaEvent, ToolUseEvent, ToolDoneEvent,
    ResponseDoneEvent, DoneEvent, ErrorEvent, CompactCallEvent, CompactEvent, SnipEvent,
    SubagentDoneEvent,
)


def _build_registry(cwd: str | None = None) -> tuple[ToolRegistry, str]:
    from skills.loader import load_skills
    from skills.skill_tool import SkillTool

    skills = load_skills(cwd)
    skill_tool = SkillTool(skills)
    skills_text = skill_tool.get_skill_list()

    registry = ToolRegistry()
    tools = [BashTool(), FileReadTool(), FileEditTool(),
             FileWriteTool(), GlobTool(), GrepTool()]
    if skills:
        tools.append(skill_tool)
    registry.register_all(tools)
    return registry, skills_text


def _load_provider_type(provider_name: str) -> str:
    """Check config.yaml for provider type (anthropic vs openai)."""
    import yaml
    from pathlib import Path
    config_path = Path("config.yaml")
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get("provider_types", {}).get(provider_name, "").lower()
    return ""


def _build_provider(config: AgentConfig):
    provider_name = config.provider.lower()
    provider_type = _load_provider_type(provider_name)
    # Known defaults: anthropic → Anthropic, others → OpenAI-compatible
    if provider_type == "anthropic" or (not provider_type and provider_name == "anthropic"):
        return AnthropicProvider(
            model=config.model or "claude-sonnet-4-6-20250514",
            api_key=config.api_key,
            base_url=config.base_url,
        )
    else:
        return OpenAICompatProvider(
            provider=provider_name, model=config.model,
            api_key=config.api_key, base_url=config.base_url,
        )


class EventHandler:
    """Base event handler — override methods in UI layer."""

    async def on_thinking(self): pass
    async def on_text_delta(self, token: str, reasoning: bool = False): pass
    async def on_tool_use(self, name: str, input_dict: dict, tool_use_id: str = ""): pass
    async def on_tool_result(self, name: str, result: str, is_error: bool, duration_ms: float = 0, tool_use_id: str = ""): pass
    async def on_response_done(self, raw: dict): pass
    async def on_done(self, final_text: str): pass
    async def on_error(self, message: str): pass
    async def on_compact_call(self, old_msg_count: int, pre_tokens: int): pass
    async def on_compact(self, pre_tokens: int, post_tokens: int, trigger: str, summary: str = ""): pass
    async def on_snip(self, groups_removed: int, tokens_before: int, tokens_after: int): pass
    async def on_subagent_done(self, agent_id: str, status: str, result: str): pass
    async def on_request(self, text: str, msg_count: int, est_tokens: int,
                         tools_count: int, model: str = ""): pass
    async def on_enqueued(self, from_name: str, message: str, source: str): pass


class AgentController:
    """Framework-agnostic Agent lifecycle manager.

    Wraps Agent creation, run_stream() event dispatch, cancel, and reconfig.
    """

    def __init__(self, config: AgentConfig, event_handler: EventHandler):
        self.config = config
        self.handler = event_handler
        self._cancel_event = asyncio.Event()
        self._current_task: asyncio.Task | None = None
        self._agent_lock = asyncio.Lock()

        self.registry, skills_text = _build_registry(config.cwd)
        self.provider = _build_provider(config)
        self._mcp_manager = None
        self._mcp_connected = False
        self.agent = Agent(
            provider=self.provider,
            registry=self.registry,
            cwd=config.cwd,
            max_turns=config.max_turns,
            max_messages=config.max_messages,
            context_window=config.context_window,
            compact_threshold=config.compact_threshold,
            reserved_output=config.reserved_output,
        )
        self.agent.skills_text = skills_text

    async def send_message(self, text: str) -> None:
        self._cancel_event.clear()
        self._current_task = asyncio.current_task()
        self.agent._loop_running = True

        try:
            async for event in self.agent.run_stream(text):
                if self._cancel_event.is_set():
                    break

                if isinstance(event, ThinkingEvent):
                    await self.handler.on_thinking()
                elif isinstance(event, TextDeltaEvent):
                    await self.handler.on_text_delta(event.token, event.reasoning)
                elif isinstance(event, ToolUseEvent):
                    await self.handler.on_tool_use(event.tool_name, event.input, event.tool_use_id)
                elif isinstance(event, ToolDoneEvent):
                    await self.handler.on_tool_result(
                        event.tool_name, event.result, event.is_error, event.duration_ms,
                        event.tool_use_id)
                elif isinstance(event, ResponseDoneEvent):
                    await self.handler.on_response_done(event.raw)
                elif isinstance(event, DoneEvent):
                    await self.handler.on_done(event.final_text)
                elif isinstance(event, ErrorEvent):
                    await self.handler.on_error(event.message)
                elif isinstance(event, CompactCallEvent):
                    await self.handler.on_compact_call(
                        event.old_msg_count, event.pre_tokens)
                elif isinstance(event, CompactEvent):
                    await self.handler.on_compact(
                        event.pre_tokens, event.post_tokens, event.trigger, event.summary)
                elif isinstance(event, SnipEvent):
                    await self.handler.on_snip(
                        event.groups_removed, event.tokens_before, event.tokens_after)
                elif isinstance(event, SubagentDoneEvent):
                    await self.handler.on_subagent_done(
                        event.agent_id, event.status, event.result)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await self.handler.on_error(f"Agent error: {e}")
        finally:
            self._current_task = None
            self.agent._loop_running = False

    async def cancel(self) -> None:
        self._cancel_event.set()
        if self._current_task is not None:
            self._current_task.cancel()
            try:
                await self._current_task
            except asyncio.CancelledError:
                pass

    def clear_history(self) -> None:
        self.agent.messages.clear()

    async def connect_mcp(self):
        """Connect MCP servers at startup. Blocks until connected or failed."""
        from mcp_integration.config import load_mcp_configs
        from mcp_integration.connection import MCPConnectionManager
        from pathlib import Path

        cwd_path = Path(self.config.cwd) if self.config.cwd else Path.cwd()
        configs = load_mcp_configs(cwd_path)
        if not configs:
            self._mcp_connected = True
            return

        self._mcp_manager = MCPConnectionManager(configs)
        await self._mcp_manager.connect_all()
        for tool in self._mcp_manager.get_tools():
            self.registry.register(tool)
        self._mcp_connected = True

    @property
    def mcp_manager(self):
        return self._mcp_manager

    def get_mcp_info(self) -> dict | None:
        """Return MCP server info for UI display, or None if no servers."""
        if not self._mcp_manager:
            return None
        statuses = self._mcp_manager.get_all_statuses()
        if not statuses:
            return None
        servers = [{"name": name, **info} for name, info in statuses.items()]
        total_tools = sum(s["tool_count"] for s in servers)
        return {
            "server_count": len(servers),
            "tool_count": total_tools,
            "servers": servers,
        }

    def reconfigure(self, new_config: AgentConfig) -> None:
        self.config = new_config
        self.provider = _build_provider(new_config)
        self.agent.provider = self.provider

    def estimate_usage(self) -> dict:
        return {
            "message_count": len(self.agent.messages),
            "estimated_tokens": self.agent.est_tokens(),
        }
