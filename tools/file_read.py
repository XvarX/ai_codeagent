"""FileRead tool — read file contents (mirrors FileReadTool/FileReadTool.ts)."""

from pathlib import Path
from typing import Any

from .base import Tool, ToolContext


class FileReadTool(Tool):
    name = "FileRead"
    description = "Read the contents of a file at the given path."
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the file to read"
            }
        },
        "required": ["file_path"]
    }

    def is_read_only(self) -> bool:
        return True

    async def call(self, input: dict[str, Any], context: ToolContext) -> str:
        path = Path(input["file_path"])
        if not path.is_absolute():
            path = context.cwd / path
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            return content
        except FileNotFoundError:
            return f"Error: File not found: {path}"
        except PermissionError:
            return f"Error: Permission denied: {path}"
        except Exception as e:
            return f"Error reading file: {e}"
