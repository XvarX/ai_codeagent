"""Tool registry — mirrors Claude Code's tools.ts registry."""

from .base import Tool


class ToolRegistry:
    """Manages tool registration, lookup, and schema generation."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def register_all(self, tools: list[Tool]) -> None:
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_enabled(self) -> list[Tool]:
        return [t for t in self._tools.values() if t.is_enabled()]

    def get_schemas(self) -> list[dict]:
        """Get API-compatible schemas for all enabled tools (管道二: API tools[])."""
        return [t.get_schema() for t in self.list_enabled()]

    def get_tool_names(self) -> list[str]:
        return [t.name for t in self.list_enabled()]
