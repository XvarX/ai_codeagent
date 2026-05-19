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
    ) -> tuple[Message, list[ToolUseBlock]]:
        """
        Stream call to LLM. Returns assistant message + extracted tool_use blocks.

        The agent loop uses the tool_use_blocks list to decide whether to
        continue (execute tools and loop back) or terminate (return to user).
        """
        ...
