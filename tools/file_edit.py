"""FileEdit tool — exact string replacement (mirrors FileEditTool/FileEditTool.ts)."""

from pathlib import Path
from typing import Any

from .base import Tool, ToolContext


class FileEditTool(Tool):
    name = "FileEdit"
    description = (
        "Make exact string replacements in a file. "
        "Provide the exact text to find (old_string) and its replacement (new_string). "
        "old_string must match exactly including whitespace."
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the file to edit"
            },
            "old_string": {
                "type": "string",
                "description": "The exact text to find and replace"
            },
            "new_string": {
                "type": "string",
                "description": "The replacement text"
            },
        },
        "required": ["file_path", "old_string", "new_string"]
    }

    async def call(self, input: dict[str, Any], context: ToolContext) -> str:
        path = Path(input["file_path"])
        if not path.is_absolute():
            path = context.cwd / path
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return f"Error: File not found: {path}"

        old = input["old_string"]
        new = input["new_string"]

        count = content.count(old)
        if count == 0:
            return f"Error: old_string not found in {path}"
        if count > 1:
            return (
                f"Error: old_string appears {count} times in {path}. "
                "Provide a larger string with more surrounding context to make it unique."
            )

        content = content.replace(old, new)
        path.write_text(content, encoding="utf-8")
        return f"Successfully edited {path}: 1 replacement made."
