"""Bash tool — execute shell commands (mirrors BashTool/BashTool.tsx)."""

import asyncio
import locale
import subprocess
from typing import Any

from .base import Tool, ToolContext


def _decode_output(data: bytes) -> str:
    """Decode shell output, falling back to system encoding if UTF-8 fails."""
    if not data:
        return ""
    text = data.decode("utf-8", errors="replace")
    if "�" in text:
        try:
            sys_enc = locale.getpreferredencoding(False)
            if sys_enc.lower() not in ("utf-8", "utf8"):
                text = data.decode(sys_enc, errors="replace")
        except (LookupError, UnicodeDecodeError):
            pass
    return text


class BashTool(Tool):
    name = "Bash"
    description = "Execute a shell command in the project's working directory."
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute"
            }
        },
        "required": ["command"]
    }

    async def call(self, input: dict[str, Any], context: ToolContext) -> str:
        command = input.get("command", "")
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(context.cwd),
            )
            stdout, stderr = await process.communicate()
            result = _decode_output(stdout)
            if stderr:
                result += "\n[stderr]\n" + _decode_output(stderr)
            if process.returncode != 0:
                result += f"\n[exit code: {process.returncode}]"
            return result.strip() or "(no output)"
        except Exception as e:
            return f"Error executing command: {e}"
