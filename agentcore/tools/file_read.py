"""FileRead tool — reads files with line numbers, offset/limit support."""

from pathlib import Path
from typing import Any

from .base import Tool, ToolContext

MAX_LINES = 2000
MAX_SIZE_STR = "256KB"
MAX_SIZE_BYTES = 256 * 1024


class FileReadTool(Tool):
    name = "FileRead"
    max_result_chars = None
    description = "Read a file from the local filesystem."
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The absolute path to the file to read"
            },
            "offset": {
                "type": "integer",
                "description": "The line number to start reading from. Only provide if the file is too large to read at once."
            },
            "limit": {
                "type": "integer",
                "description": "The number of lines to read. Only provide if the file is too large to read at once."
            },
        },
        "required": ["file_path"]
    }

    def is_read_only(self) -> bool:
        return True

    async def call(self, input: dict[str, Any], context: ToolContext) -> str:
        path = Path(input["file_path"])
        if not path.is_absolute():
            path = (context.cwd / path).resolve()
        else:
            path = path.resolve()

        offset = max(1, int(input.get("offset", 0) or 0))
        limit = int(input.get("limit", 0) or 0)

        if not path.exists():
            return f"Error: File not found: {path}"
        if path.is_dir():
            return f"Error: Path is a directory, not a file: {path}"

        size = path.stat().st_size
        if size > MAX_SIZE_BYTES and offset <= 1 and not limit:
            return (
                f"Error: File is too large ({_format_size(size)}). "
                f"Files larger than {MAX_SIZE_STR} require offset and limit parameters."
            )

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except PermissionError:
            return f"Error: Permission denied: {path}"
        except Exception as e:
            return f"Error reading file: {e}"

        if not content:
            return "<system-reminder>Warning: the file exists but the contents are empty.</system-reminder>"

        lines = content.splitlines()
        total_lines = len(lines)

        if offset > total_lines:
            return (
                f"<system-reminder>Warning: the file exists but the provided offset "
                f"({offset}) exceeds the total number of lines ({total_lines}).</system-reminder>"
            )

        end_line = offset + limit - 1 if limit > 0 else min(offset + MAX_LINES - 1, total_lines)
        end_line = min(end_line, total_lines)

        selected = lines[offset - 1:end_line]
        result = _add_line_numbers(selected, start=offset)

        if end_line < total_lines:
            result += f"\n\n<system-reminder>Showing lines {offset}-{end_line} of {total_lines}. Use offset={end_line + 1} to read more.</system-reminder>"

        return result


def _add_line_numbers(lines: list[str], start: int = 1) -> str:
    """Format lines in cat -n style: line_number<tab>content."""
    out = []
    for i, line in enumerate(lines):
        out.append(f"{start + i}\t{line}")
    return "\n".join(out)


def _format_size(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    elif n < 1024 * 1024:
        return f"{n / 1024:.1f}KB"
    else:
        return f"{n / (1024 * 1024):.1f}MB"
