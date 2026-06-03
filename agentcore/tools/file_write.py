"""FileWrite tool — create or overwrite files (mirrors FileWriteTool/FileWriteTool.ts)."""

from pathlib import Path
from typing import Any

from .base import Tool, ToolContext


class FileWriteTool(Tool):
    name = "FileWrite"
    description = (
        "Create a new file or completely overwrite an existing file "
        "with the given content."
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the file to write"
            },
            "content": {
                "type": "string",
                "description": "The content to write to the file"
            },
        },
        "required": ["file_path", "content"]
    }

    async def call(self, input: dict[str, Any], context: ToolContext) -> str:
        path = Path(input["file_path"])
        if not path.is_absolute():
            path = context.cwd / path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(input["content"], encoding="utf-8")
            return f"Successfully wrote to {path} ({len(input['content'])} characters)."
        except Exception as e:
            return f"Error writing file: {e}"
