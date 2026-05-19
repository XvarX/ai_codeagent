"""Shared type definitions for the agent framework."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolUseBlock:
    """Represents a tool_use content block from an LLM response."""
    tool_use_id: str
    tool_name: str
    input: dict[str, Any]


@dataclass
class Message:
    """Base message in the conversation."""
    role: str  # "user" | "assistant"
    content: str = ""
    tool_use_blocks: list[ToolUseBlock] = field(default_factory=list)
    tool_use_id: str | None = None  # for tool_result messages

    @property
    def is_tool_result(self) -> bool:
        return self.tool_use_id is not None

    @property
    def has_tool_uses(self) -> bool:
        return len(self.tool_use_blocks) > 0


@dataclass
class ToolResult:
    """Result returned by a tool's call() method."""
    content: str
    is_error: bool = False


@dataclass
class PermissionResult:
    """Result of a permission check."""
    allowed: bool = True
    reason: str = ""
