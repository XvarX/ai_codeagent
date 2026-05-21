"""Grep tool — regex content search (mirrors GrepTool/GrepTool.ts)."""

import re
from pathlib import Path
from typing import Any

from .base import Tool, ToolContext


class GrepTool(Tool):
    name = "Grep"
    max_result_chars = 20_000  # Aligns to Claude Code
    description = (
        "Search file contents using a regex pattern. "
        "Returns file paths and matching lines."
    )
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "The regex pattern to search for"
            },
            "path": {
                "type": "string",
                "description": "Directory to search in (default: cwd)"
            },
        },
        "required": ["pattern"]
    }

    def is_read_only(self) -> bool:
        return True

    async def call(self, input: dict[str, Any], context: ToolContext) -> str:
        pattern = input["pattern"]
        search_dir = Path(input.get("path", context.cwd))
        try:
            compiled = re.compile(pattern)
        except re.error as e:
            return f"Error: Invalid regex pattern: {e}"

        results: list[str] = []
        seen = 0
        try:
            for file_path in sorted(search_dir.rglob("*")):
                if file_path.is_dir() or ".git" in file_path.parts:
                    continue
                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                for line_no, line in enumerate(content.splitlines(), 1):
                    if compiled.search(line):
                        results.append(f"{file_path}:{line_no}: {line.strip()}")
                        seen += 1
                        if seen >= 200:
                            break
                if seen >= 200:
                    break
            if not results:
                return f"No matches found for pattern: {pattern}"
            return "\n".join(results)
        except Exception as e:
            return f"Error in grep search: {e}"
