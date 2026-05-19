"""Tool abstract base class — mirrors Claude Code's Tool interface (Tool.ts)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ToolContext:
    """Context passed to tools during execution (mirrors ToolUseContext from Tool.ts)."""
    cwd: Path
    messages: list = field(default_factory=list)


class Tool(ABC):
    """
    Abstract base class for all tools.
    Mirrors the Tool type from Tool.ts:
    - name, description, parameters → schema for the LLM
    - call() → execution logic
    """

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)

    @abstractmethod
    async def call(self, input: dict[str, Any], context: ToolContext) -> str:
        """Execute the tool with given input and context. Returns result string."""
        ...

    def is_enabled(self) -> bool:
        return True

    def is_read_only(self) -> bool:
        return False

    def get_schema(self) -> dict[str, Any]:
        """Serialize to API-compatible JSON Schema (mirrors toolToAPISchema)."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
