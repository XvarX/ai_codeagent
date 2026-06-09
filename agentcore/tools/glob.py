"""Glob tool — fast file pattern matching via ripgrep (mirrors GlobTool/GlobTool.ts)."""

import os
import subprocess
from pathlib import Path
from typing import Any

from .base import Tool, ToolContext
from .grep import _find_rg

MAX_RESULTS = 100


def _to_relative_g(file_path: str, cwd: str) -> str:
    """Convert absolute path to relative (vs cwd)."""
    try:
        return str(Path(file_path).relative_to(Path(cwd)))
    except (ValueError, TypeError):
        return file_path


class GlobTool(Tool):
    name = "Glob"
    max_result_chars = 100_000

    description = (
        "- Fast file pattern matching tool that works with any codebase size\n"
        "- Supports glob patterns like \"**/*.js\" or \"src/**/*.ts\"\n"
        "- Returns matching file paths sorted by modification time\n"
        "- Use this tool when you need to find files by name patterns\n"
        "- When you are doing an open ended search that may require multiple rounds of globbing and grepping, "
        "use the Agent tool instead"
    )

    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "The glob pattern to match files against"
            },
            "path": {
                "type": "string",
                "description": "The directory to search in. If not specified, the current working directory will be used. "
                               "IMPORTANT: Omit this field to use the default directory. "
                               "DO NOT enter \"undefined\" or \"null\" - simply omit it for the default behavior. "
                               "Must be a valid directory path if provided."
            },
        },
        "required": ["pattern"]
    }

    def is_read_only(self) -> bool:
        return True

    def is_concurrency_safe(self) -> bool:
        return True

    async def call(self, input: dict[str, Any], context: ToolContext) -> str:
        pattern = input["pattern"]
        search_path = input.get("path") or str(context.cwd)

        try:
            rg = _find_rg()
        except RuntimeError as e:
            # Fallback to Python glob
            import glob as glob_mod
            try:
                results = sorted(str(p) for p in Path(search_path).rglob(pattern))
                results = [r for r in results if Path(r).is_file()]
                if not results:
                    return "No files found"
                results = results[:MAX_RESULTS]
                return "\n".join(results)
            except Exception as e2:
                return f"Error: {e}\nPython glob fallback also failed: {e2}"

        cmd = [
            rg, "--files", "--glob", pattern,
            "--sortr", "modified",
            "--no-config", "--no-ignore-global",
            "--", search_path,
        ]

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=30, cwd=str(context.cwd),
                env={**os.environ, "RIPGREP_CONFIG_PATH": "/dev/null"},
            )
        except subprocess.TimeoutExpired:
            return "Error: Glob search timed out after 30s"
        except Exception as e:
            return f"Error executing glob: {e}"

        if proc.returncode > 1:
            return f"Error in glob search: {proc.stderr.strip()}"
        if proc.returncode == 1:
            return "No files found"

        filenames = [f.strip() for f in proc.stdout.splitlines() if f.strip()]
        num_files = len(filenames)
        if num_files == 0:
            return "No files found"

        # Convert absolute paths to relative
        cwd_str = str(context.cwd)
        filenames = [_to_relative_g(f, cwd_str) for f in filenames]

        truncated = num_files > MAX_RESULTS
        filenames = filenames[:MAX_RESULTS]

        result = "\n".join(filenames)
        if truncated:
            result += "\n(Results are truncated. Consider using a more specific path or pattern.)"

        return result
