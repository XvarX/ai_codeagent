"""Grep tool — regex content search via ripgrep (mirrors GrepTool/GrepTool.ts)."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .base import Tool, ToolContext

_RG_PATH: str | None = None

VCS_EXCLUDES = [
    "!.git/*", "!.svn/*", "!.hg/*", "!.bzr/*",
    "!.jj/*", "!.sl/*",
]


def _find_rg() -> str:
    """Find ripgrep binary. Checks env, bundled, and system PATH."""
    global _RG_PATH
    if _RG_PATH:
        return _RG_PATH

    # 1. Explicit env var
    env_rg = os.environ.get("AGENT_RG_PATH")
    if env_rg and Path(env_rg).exists():
        _RG_PATH = env_rg
        return _RG_PATH

    # 2. Bundled: next to the exe (PyInstaller) or in agentcore/
    exe_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent
    bundled = exe_dir / "rg.exe"
    if bundled.exists():
        _RG_PATH = str(bundled)
        return _RG_PATH

    # 3. System PATH
    import shutil
    system_rg = shutil.which("rg")
    if system_rg:
        _RG_PATH = system_rg
        return _RG_PATH

    raise RuntimeError(
        "ripgrep (rg) not found. Install it from https://github.com/BurntSushi/ripgrep "
        "or set AGENT_RG_PATH to the binary location."
    )


HEAD_LIMIT_DEFAULT = 250


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
                "description": "Output mode: \"content\" shows matching lines (supports -A/-B/-C context, -n line numbers, head_limit), "
                               "\"files_with_matches\" shows file paths (supports head_limit), "
                               "\"count\" shows match counts (supports head_limit). Defaults to \"files_with_matches\"."
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
                "description": "File type to search (rg --type). Common types: js, py, rust, go, java, etc. More efficient than include for standard file types."
            },
            "head_limit": {
                "type": "integer",
                "description": "Limit output to first N lines/entries, equivalent to \"| head -N\". "
                               "Works across all output modes: content (limits output lines), files_with_matches (limits file paths), "
                               "count (limits count entries). Defaults to 250 when unspecified. Pass 0 for unlimited (use sparingly — large result sets waste context)."
            },
            "offset": {
                "type": "integer",
                "description": "Skip first N lines/entries before applying head_limit, equivalent to \"| tail -n +N | head -N\". "
                               "Works across all output modes. Defaults to 0."
            },
            "multiline": {
                "type": "boolean",
                "description": "Enable multiline mode where . matches newlines and patterns can span lines (rg -U --multiline-dotall). Default: false."
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
        head_limit = int(input.get("head_limit", 0) or 0)
        if head_limit < 0:
            head_limit = 0
        use_default_limit = "head_limit" not in input or input["head_limit"] is None
        offset = int(input.get("offset", 0) or 0)

        try:
            rg = _find_rg()
        except RuntimeError as e:
            return f"Error: {e}"

        cmd = [rg, "--no-config", "--no-ignore-global", "--hidden",
               "--max-columns", "500", "--max-columns-preview"]

        # VCS directory exclusion
        for excl in VCS_EXCLUDES:
            cmd.extend(["--iglob", excl])

        # Mode
        if output_mode == "files_with_matches":
            cmd.extend(["--files-with-matches", "--sort", "modified"])
        elif output_mode == "count":
            cmd.extend(["--count"])
        else:
            cmd.extend(["--no-heading", "--with-filename"])
            show_line_numbers = True
            if "-n" in input and input["-n"] is False:
                show_line_numbers = False
            if show_line_numbers:
                cmd.append("--line-number")

        # Context lines
        context_before = int(input.get("-B", 0) or 0)
        context_after = int(input.get("-A", 0) or 0)
        context_around = int(input.get("-C", 0) or 0) or int(input.get("context", 0) or 0)
        if context_before:
            cmd.extend(["-B", str(context_before)])
        if context_after:
            cmd.extend(["-A", str(context_after)])
        if context_around:
            cmd.extend(["-C", str(context_around)])

        # Case insensitive
        if input.get("-i"):
            cmd.append("-i")

        # File type filter
        file_type = input.get("type")
        if file_type:
            cmd.extend(["--type", file_type])

        # Glob filter — split by comma and whitespace (mirrors source)
        glob_pattern = input.get("glob")
        if glob_pattern:
            for g in _split_glob(glob_pattern):
                cmd.extend(["--glob", g])

        # Multiline
        if input.get("multiline"):
            cmd.append("--multiline-dotall")

        # Use -e for safe pattern handling, then path
        cmd.extend(["-e", pattern, "--", search_path])

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=30, cwd=str(context.cwd),
                env={**os.environ, "RIPGREP_CONFIG_PATH": "/dev/null"},
            )
        except subprocess.TimeoutExpired:
            return "Error: Grep search timed out after 30s"
        except FileNotFoundError:
            return f"Error: ripgrep binary not found at: {rg}"
        except Exception as e:
            return f"Error executing grep: {e}"

        if proc.returncode > 1:
            return f"Error in grep search: {proc.stderr.strip()}"
        if proc.returncode == 1:
            if output_mode == "files_with_matches":
                return "No files found"
            return "No matches found"

        raw = proc.stdout
        cwd_str = str(context.cwd)

        if output_mode == "files_with_matches":
            filenames = [_to_relative(f.strip(), cwd_str) for f in raw.splitlines() if f.strip()]
            num_files = len(filenames)
            if num_files == 0:
                return "No files found"
            applied_limit, applied_offset = _apply_pagination(head_limit, offset, use_default_limit)
            filenames = filenames[applied_offset:applied_offset + applied_limit] if applied_limit else filenames[applied_offset:]
            limit_info = _format_limit_info(applied_limit if applied_limit > 0 else None, applied_offset if applied_offset > 0 else None)
            result = f"Found {num_files} {'file' if num_files == 1 else 'files'}{' ' + limit_info if limit_info else ''}\n" + "\n".join(filenames)
            return result

        elif output_mode == "count":
            lines = [l.strip() for l in raw.splitlines() if l.strip()]
            num_files = len(lines)
            total_matches = 0
            for line in lines:
                parts = line.rsplit(":", 1)
                try:
                    total_matches += int(parts[-1])
                except (ValueError, IndexError):
                    pass
            applied_limit, applied_offset = _apply_pagination(head_limit, offset, use_default_limit)
            lines = [_to_relative(l, cwd_str) for l in lines]
            lines = lines[applied_offset:applied_offset + applied_limit] if applied_limit else lines[applied_offset:]
            limit_info = _format_limit_info(applied_limit if applied_limit > 0 else None, applied_offset if applied_offset > 0 else None)
            raw_content = "\n".join(lines)
            pagination = f" with pagination = {limit_info}" if limit_info else ""
            summary = (
                f"\n\nFound {total_matches} total {'occurrence' if total_matches == 1 else 'occurrences'} "
                f"across {num_files} {'file' if num_files == 1 else 'files'}.{pagination}"
            )
            return raw_content + summary

        else:
            # content mode — rg with --line-number returns "file:line:content" format
            # Strip line numbers from relative paths that contain ':' (e.g., "./foo/bar.py:42:text")
            lines = [l.strip() for l in raw.splitlines() if l.strip()]
            # Convert absolute paths to relative in output
            rel_lines = []
            for line in lines:
                # rg output format: /abs/path/to/file:line_num:content
                # Convert to: rel/path/to/file:line_num:content
                if line.startswith(cwd_str):
                    # Find the second colon (after path) to split path from line:content
                    rel_path = _to_relative(line, cwd_str)
                    # rel_path is "rel/path:line:content" already since only the prefix was replaced
                    rel_lines.append(rel_path)
                else:
                    rel_lines.append(line)
            applied_limit, applied_offset = _apply_pagination(head_limit, offset, use_default_limit)
            rel_lines = rel_lines[applied_offset:applied_offset + applied_limit] if applied_limit else rel_lines[applied_offset:]
            limit_info = _format_limit_info(applied_limit if applied_limit > 0 else None, applied_offset if applied_offset > 0 else None)
            result_content = "\n".join(rel_lines) if rel_lines else "No matches found"
            if limit_info:
                result_content += f"\n\n[Showing results with pagination = {limit_info}]"
            return result_content


def _split_glob(pattern: str) -> list[str]:
    """Split glob pattern by comma/whitespace, respecting braces. Mirrors source."""
    import re
    parts = re.split(r",\s*|\s+", pattern)
    return [p for p in parts if p]


def _to_relative(file_path: str, cwd: str) -> str:
    """Convert absolute path to relative (vs cwd)."""
    try:
        p = Path(file_path)
        c = Path(cwd)
        rel = p.relative_to(c)
        return str(rel)
    except (ValueError, TypeError):
        return file_path


def _format_limit_info(limit: int | None, ofs: int | None) -> str:
    parts = []
    if limit is not None:
        parts.append(f"limit: {limit}")
    if ofs:
        parts.append(f"offset: {ofs}")
    return ", ".join(parts)


def _apply_pagination(head_limit: int, offset: int, use_default: bool) -> tuple[int, int]:
    """Returns (effective_limit, effective_offset)."""
    if use_default and head_limit == 0:
        head_limit = HEAD_LIMIT_DEFAULT
    return head_limit, offset
