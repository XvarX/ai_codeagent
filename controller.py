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
    ResponseDoneEvent, DoneEvent, ErrorEvent, CompactEvent,
)


def _build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register_all([
        BashTool(), FileReadTool(), FileEditTool(),
        FileWriteTool(), GlobTool(), GrepTool(),
    ])
    return registry


def _build_provider(config: AgentConfig):
    provider_name = config.provider.lower()
    if provider_name == "anthropic":
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
    async def on_text_delta(self, token: str): pass
    async def on_tool_use(self, name: str, input_dict: dict): pass
    async def on_tool_result(self, name: str, result: str, is_error: bool): pass
    async def on_response_done(self, raw: dict): pass
    async def on_done(self, final_text: str): pass
    async def on_error(self, message: str): pass
    async def on_compact(self, pre_tokens: int, post_tokens: int, trigger: str): pass


class AgentController:
    """Framework-agnostic Agent lifecycle manager.

    Wraps Agent creation, run_stream() event dispatch, cancel, and reconfig.
    """

    def __init__(self, config: AgentConfig, event_handler: EventHandler):
        self.config = config
        self.handler = event_handler
        self._cancel_event = asyncio.Event()
        self._current_task: asyncio.Task | None = None

        self.registry = _build_registry()
        self.provider = _build_provider(config)
        self.agent = Agent(
            provider=self.provider,
            registry=self.registry,
            cwd=config.cwd,
            max_turns=config.max_turns,
            max_messages=config.max_messages,
        )

    async def send_message(self, text: str) -> None:
        self._cancel_event.clear()
        self._current_task = asyncio.current_task()

        try:
            async for event in self.agent.run_stream(text):
                if self._cancel_event.is_set():
                    break

                if isinstance(event, ThinkingEvent):
                    await self.handler.on_thinking()
                elif isinstance(event, TextDeltaEvent):
                    await self.handler.on_text_delta(event.token)
                elif isinstance(event, ToolUseEvent):
                    await self.handler.on_tool_use(event.tool_name, event.input)
                elif isinstance(event, ToolDoneEvent):
                    await self.handler.on_tool_result(
                        event.tool_name, event.result, event.is_error)
                elif isinstance(event, ResponseDoneEvent):
                    await self.handler.on_response_done(event.raw)
                elif isinstance(event, DoneEvent):
                    await self.handler.on_done(event.final_text)
                elif isinstance(event, ErrorEvent):
                    await self.handler.on_error(event.message)
                elif isinstance(event, CompactEvent):
                    await self.handler.on_compact(
                        event.pre_tokens, event.post_tokens, event.trigger)
        except asyncio.CancelledError:
            pass
        finally:
            self._current_task = None

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

    def reconfigure(self, new_config: AgentConfig) -> None:
        self.config = new_config
        self.provider = _build_provider(new_config)
        self.agent.provider = self.provider
        self.agent.messages.clear()

    def estimate_usage(self) -> dict:
        return {
            "message_count": len(self.agent.messages),
            "estimated_tokens": self.agent._est_tokens(),
        }
