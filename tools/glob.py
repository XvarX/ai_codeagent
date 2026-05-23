"""Glob tool — file pattern matching (mirrors GlobTool/GlobTool.ts)."""

import glob as glob_mod
from pathlib import Path
from typing import Any

from .base import Tool, ToolContext


class GlobTool(Tool):
    name = "Glob"
    description = "Find files matching a glob pattern (e.g., '**/*.py', 'src/**/*.ts'). Supports absolute paths."
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
            cwd_str = str(context.cwd.resolve())
            # If absolute, use glob.glob directly (supports absolute patterns)
            if Path(pattern).is_absolute() or pattern.startswith("/"):
                results = sorted(glob_mod.glob(pattern, recursive=True))
            elif pattern.startswith(cwd_str):
                # Absolute path to CWD subdirectory — make relative
                rel = pattern[len(cwd_str):].lstrip("\\/")
                results = sorted(str(p) for p in context.cwd.glob(rel))
            else:
                # Relative — search from CWD
                results = sorted(str(p) for p in context.cwd.glob(pattern))
            if not results:
                return f"No files matched pattern: {pattern}"
            return "\n".join(results[:200])
        except Exception as e:
            return f"Error in glob search: {e}"
