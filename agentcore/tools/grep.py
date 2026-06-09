"""Grep tool — regex content search via ripgrep (mirrors GrepTool/GrepTool.ts)."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .base import Tool, ToolContext

_RG_PATH: str | None = None

VCS_EXCLUDES = [".git", ".svn", ".hg", ".bzr", ".jj", ".sl"]


def _find_rg() -> str:
    """Find ripgrep binary. Checks env, bundled, and system PATH."""
    global _RG_PATH
    if _RG_PATH:
        return _RG_PATH
    env_rg = os.environ.get("AGENT_RG_PATH")
    if env_rg and Path(env_rg).exists():
        _RG_PATH = env_rg
        return _RG_PATH
    exe_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent
    bundled = exe_dir / "rg.exe"
    if bundled.exists():
        _RG_PATH = str(bundled)
        return _RG_PATH
    import shutil
    system_rg = shutil.which("rg")
    if system_rg:
        _RG_PATH = system_rg
        return _RG_PATH
    raise RuntimeError(
        "ripgrep (rg) not found. Install it from https://github.com/BurntSushi/ripgrep "
        "or set AGENT_RG_PATH to the binary location."
    )


DEFAULT_HEAD_LIMIT = 250


class GrepTool(Tool):
    name = "Grep"
    max_result_chars = 20_000

    description = (
        "A powerful search tool built on ripgrep\n\n"
        "Usage:\n"
        "- ALWAYS use Grep for search tasks. NEVER invoke `grep` or `rg` as a Bash command. "
        "The Grep tool has been optimized for correct permissions and access.\n"
        "- Supports full regex syntax (e.g., \"log.*Error\", \"function\\s+\\w+\")\n"
        "- Filter files with glob parameter (e.g., \"*.js\", \"**/*.tsx\") or type parameter (e.g., \"js\", \"py\", \"rust\")\n"
        "- Output modes: \"content\" shows matching lines, \"files_with_matches\" shows only file paths (default), \"count\" shows match counts\n"
        "- Use Agent tool for open-ended searches requiring multiple rounds\n"
        "- Pattern syntax: Uses ripgrep (not grep) - literal braces need escaping (use `interface\\{\\}` to find `interface{}` in Go code)\n"
        "- Multiline matching: By default patterns match within single lines only. "
        "For cross-line patterns like `struct \\{[\\s\\S]*?field`, use `multiline: true`"
    )

    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "The regular expression pattern to search for in file contents"
            },
            "path": {
                "type": "string",
                "description": "File or directory to search in (rg PATH). Defaults to current working directory."
            },
            "glob": {
                "type": "string",
                "description": "Glob pattern to filter files (e.g. \"*.js\", \"*.{ts,tsx}\") - maps to rg --glob"
            },
            "output_mode": {
                "type": "string",
                "enum": ["content", "files_with_matches", "count"],
                "description": "Output mode: \"content\" shows matching lines, \"files_with_matches\" shows file paths (default), \"count\" shows match counts"
            },
            "-B": {
                "type": "integer",
                "description": "Number of lines to show before each match (rg -B). Requires output_mode: \"content\", ignored otherwise."
            },
            "-A": {
                "type": "integer",
                "description": "Number of lines to show after each match (rg -A). Requires output_mode: \"content\", ignored otherwise."
            },
            "-C": {
                "type": "integer",
                "description": "Alias for context."
            },
            "context": {
                "type": "integer",
                "description": "Number of lines to show before and after each match (rg -C). Requires output_mode: \"content\", ignored otherwise."
            },
            "-n": {
                "type": "boolean",
                "description": "Show line numbers in output (rg -n). Requires output_mode: \"content\", ignored otherwise. Defaults to true."
            },
            "-i": {
                "type": "boolean",
                "description": "Case insensitive search (rg -i)"
            },
            "type": {
                "type": "string",
                "description": "File type to search (rg --type). Common types: js, py, rust, go, java, etc."
            },
            "head_limit": {
                "type": "integer",
                "description": "Limit output to first N lines/entries, equivalent to \"| head -N\". Defaults to 250. Pass 0 for unlimited."
            },
            "offset": {
                "type": "integer",
                "description": "Skip first N lines/entries before applying head_limit, equivalent to \"| tail -n +N | head -N\". Defaults to 0."
            },
            "multiline": {
                "type": "boolean",
                "description": "Enable multiline mode. Default: false."
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
        output_mode = input.get("output_mode") or "files_with_matches"
        limit = input.get("head_limit")
        limit = int(limit) if limit is not None else None
        offset = int(input.get("offset", 0) or 0)

        try:
            rg = _find_rg()
        except RuntimeError as e:
            return f"Error: {e}"

        cmd = [rg, "--no-config", "--no-ignore-global", "--hidden",
               "--max-columns", "500"]

        # VCS directory exclusion
        for d in VCS_EXCLUDES:
            cmd.extend(["--glob", "!" + d])

        # Mode
        is_content = output_mode == "content"
        if output_mode == "files_with_matches":
            cmd.extend(["-l", "--sortr", "modified"])
        elif output_mode == "count":
            cmd.extend(["-c"])

        # Content-only flags
        if is_content:
            if not ("-n" in input and input["-n"] is False):
                cmd.append("-n")
            # Context lines — context takes precedence over -C (mirrors source)
            ctx = input.get("context")
            ctx_c = input.get("-C")
            if ctx is not None:
                cmd.extend(["-C", str(int(ctx))])
            elif ctx_c is not None:
                cmd.extend(["-C", str(int(ctx_c))])
            else:
                if input.get("-B"):
                    cmd.extend(["-B", str(int(input["-B"]))])
                if input.get("-A"):
                    cmd.extend(["-A", str(int(input["-A"]))])

        # Case insensitive
        if input.get("-i"):
            cmd.append("-i")

        # File type filter
        file_type = input.get("type")
        if file_type:
            cmd.extend(["--type", file_type])

        # Glob filter — split by whitespace, respecting braces (mirrors source)
        glob_pattern = input.get("glob")
        if glob_pattern:
            for g in _split_glob(glob_pattern):
                cmd.extend(["--glob", g])

        # Multiline
        if input.get("multiline"):
            cmd.extend(["-U", "--multiline-dotall"])

        # Pattern (use -e only if starts with '-')
        if pattern.startswith("-"):
            cmd.extend(["-e", pattern])
        else:
            cmd.append(pattern)

        # Search path
        cmd.append(search_path)

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=30, cwd=str(context.cwd),
                env={**os.environ, "RIPGREP_CONFIG_PATH": "/dev/null"},
            )
        except subprocess.TimeoutExpired:
            return "Error: Grep search timed out after 30s"
        except Exception as e:
            return f"Error executing grep: {e}"

        if proc.returncode > 1:
            return f"Error in grep search: {proc.stderr.strip()}"
        if proc.returncode == 1:
            return "No files found" if output_mode == "files_with_matches" else "No matches found"

        raw = proc.stdout
        cwd_str = str(context.cwd)

        if output_mode == "files_with_matches":
            filenames = [_to_relative(f.strip(), cwd_str) for f in raw.splitlines() if f.strip()]
            total_files = len(filenames)
            if total_files == 0:
                return "No files found"
            effective_limit = limit if limit is not None else DEFAULT_HEAD_LIMIT
            displayed = filenames[offset:offset + effective_limit] if effective_limit > 0 else filenames[offset:]
            was_truncated = len(displayed) < total_files or (effective_limit > 0 and len(displayed) < total_files)
            limit_info = _format_limit_info(effective_limit if was_truncated and effective_limit > 0 else None, offset if offset > 0 else None)
            result = f"Found {len(displayed)} {'file' if len(displayed) == 1 else 'files'}{' ' + limit_info if limit_info else ''}\n" + "\n".join(displayed)
            return result

        elif output_mode == "count":
            lines = [l.strip() for l in raw.splitlines() if l.strip()]
            total_files = len(lines)
            total_matches = 0
            for line in lines:
                parts = line.rsplit(":", 1)
                try:
                    total_matches += int(parts[-1])
                except (ValueError, IndexError):
                    pass
            effective_limit = limit if limit is not None else DEFAULT_HEAD_LIMIT
            lines = [_to_relative(l, cwd_str) for l in lines]
            displayed = lines[offset:offset + effective_limit] if effective_limit > 0 else lines[offset:]
            was_truncated = len(displayed) < total_files or (effective_limit > 0 and len(displayed) < total_files)
            limit_info = _format_limit_info(effective_limit if was_truncated and effective_limit > 0 else None, offset if offset > 0 else None)
            pagination = f" with pagination = {limit_info}" if limit_info else ""
            summary = (
                f"\n\nFound {total_matches} total {'occurrence' if total_matches == 1 else 'occurrences'} "
                f"across {len(displayed)} {'file' if len(displayed) == 1 else 'files'}.{pagination}"
            )
            return "\n".join(displayed) + summary

        else:
            # content mode
            lines = raw.splitlines()
            total_lines = len(lines)
            effective_limit = limit if limit is not None else DEFAULT_HEAD_LIMIT
            displayed = lines[offset:offset + effective_limit] if effective_limit > 0 else lines[offset:]
            was_truncated = (effective_limit > 0 and len(displayed) < total_lines) or (offset > 0)
            # Convert absolute paths to relative
            prefix = cwd_str + os.sep
            rel_lines = []
            for line in displayed:
                stripped = line.rstrip("\n\r")
                if stripped.startswith(prefix):
                    rel_lines.append(stripped[len(prefix):])
                elif stripped.startswith(cwd_str):
                    rel_lines.append(stripped[len(cwd_str) + 1:])
                else:
                    rel_lines.append(stripped)
            limit_info = _format_limit_info(effective_limit if was_truncated and effective_limit > 0 else None, offset if offset > 0 else None)
            result_content = "\n".join(rel_lines) if rel_lines else "No matches found"
            if limit_info:
                result_content += f"\n\n[Showing results with pagination = {limit_info}]"
            return result_content


def _split_glob(pattern: str) -> list[str]:
    """Split glob pattern by whitespace, preserving brace groups (mirrors source)."""
    parts = pattern.split()
    result = []
    for p in parts:
        if "{" in p and "}" in p:
            result.append(p)
        else:
            result.extend([x.strip() for x in p.split(",") if x.strip()])
    return result


def _to_relative(file_path: str, cwd: str) -> str:
    """Convert absolute path to relative (vs cwd)."""
    try:
        return str(Path(file_path).relative_to(Path(cwd)))
    except (ValueError, TypeError):
        return file_path


def _format_limit_info(limit: int | None, ofs: int | None) -> str:
    parts = []
    if limit is not None:
        parts.append(f"limit: {limit}")
    if ofs:
        parts.append(f"offset: {ofs}")
    return ", ".join(parts)
