"""Bash tool — execute shell commands (mirrors BashTool/BashTool.tsx)."""

import asyncio
import subprocess
from typing import Any

from .base import Tool, ToolContext


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
            result = stdout.decode("utf-8", errors="replace")
            if stderr:
                result += "\n[stderr]\n" + stderr.decode("utf-8", errors="replace")
            if process.returncode != 0:
                result += f"\n[exit code: {process.returncode}]"
            return result.strip() or "(no output)"
        except Exception as e:
            return f"Error executing command: {e}"
