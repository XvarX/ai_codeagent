"""Base provider abstraction — mirrors services/api/claude.ts callModel interface."""

from abc import ABC, abstractmethod
from core_types import Message, ToolUseBlock


class BaseProvider(ABC):
    """Abstract base for LLM providers (Anthropic, OpenAI, GLM, DeepSeek)."""

    @abstractmethod
    async def call(
        self,
        messages: list[Message],
        tools: list[dict],
        system: str,
    ) -> tuple[Message, list[ToolUseBlock], dict]:
        """
        Stream call to LLM. Returns (assistant_msg, tool_use_blocks, raw_response).

        The agent loop uses the tool_use_blocks list to decide whether to
        continue (execute tools and loop back) or terminate (return to user).

        raw_response contains provider-specific metadata (token usage, model,
        finish_reason, etc.).
        """
        ...

    @abstractmethod
    async def call_stream(
        self,
        messages: list[Message],
        tools: list[dict],
        system: str,
    ):
        """
        Streaming call to LLM. Yields events: TextDeltaEvent, ToolUseEvent,
        ResponseDoneEvent, ErrorEvent.

        Returns an AsyncGenerator that yields events as they arrive.
        """
        ...
