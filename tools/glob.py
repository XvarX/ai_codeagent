"""Glob tool — file pattern matching (mirrors GlobTool/GlobTool.ts)."""

from pathlib import Path
from typing import Any

from .base import Tool, ToolContext


class GlobTool(Tool):
    name = "Glob"
    description = "Find files matching a glob pattern (e.g., '**/*.py', 'src/**/*.ts')."
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "The glob pattern to match file paths"
            },
        },
        "required": ["pattern"]
    }

    def is_read_only(self) -> bool:
        return True

    async def call(self, input: dict[str, Any], context: ToolContext) -> str:
        pattern = input["pattern"]
        try:
            # Convert absolute patterns to relative (Path.glob requires relative)
            cwd_str = str(context.cwd.resolve())
            if pattern.startswith(cwd_str):
                pattern = pattern[len(cwd_str):].lstrip("\\/")
            elif pattern.startswith("/") or (len(pattern) > 1 and pattern[1] == ":"):
                return f"Error: absolute patterns outside CWD are unsupported. Use a relative pattern within {cwd_str}"
            results = sorted(str(p) for p in context.cwd.glob(pattern))
            if not results:
                return f"No files matched pattern: {pattern}"
            return "\n".join(results[:200])
        except Exception as e:
            return f"Error in glob search: {e}"
