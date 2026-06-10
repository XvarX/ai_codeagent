"""FileBrowserHandler — browse, read, write, and search project files.

Designed to be used by ws_server.py to serve file-browsing WebSocket
requests.  All paths are relative to a project root (``cwd``) and path
safety is enforced: no traversal outside the project root is allowed.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BINARY_EXTENSIONS: set[str] = {
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".tif", ".tiff", ".webp",
    ".svg",
    # Audio / Video
    ".mp3", ".mp4", ".wav", ".flac", ".ogg", ".avi", ".mov", ".mkv", ".wmv",
    # Archives
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    # Compiled / Binaries
    ".exe", ".dll", ".so", ".dylib", ".bin", ".obj", ".o", ".pyc", ".pyo",
    ".class", ".wasm",
    # Documents
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    # Database
    ".db", ".sqlite", ".sqlite3",
    # Fonts
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    # Other
    ".iso", ".dmg", ".jar", ".nupkg",
}

EXT_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".vue": "vue",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".json": "json",
    ".md": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".bat": "bat",
    ".cmd": "bat",
    ".sql": "sql",
    ".xml": "xml",
    ".ini": "ini",
    ".cfg": "ini",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".lua": "lua",
    ".r": "r",
    ".R": "r",
    ".m": "objective-c",
    ".mm": "objective-c",
    ".pl": "perl",
    ".pm": "perl",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hs": "haskell",
    ".scala": "scala",
    ".clj": "clojure",
    ".dart": "dart",
    ".proto": "protobuf",
    ".tf": "hcl",
    ".lock": "lockfile",
    ".mod": "go-mod",
    ".sum": "checksum",
}

# Filenames (case-insensitive) that map to a language
_SPECIAL_FILE_LANGUAGE: dict[str, str] = {
    "dockerfile": "dockerfile",
    "dockerfile.dev": "dockerfile",
    "dockerfile.prod": "dockerfile",
    "makefile": "makefile",
    "gnumakefile": "makefile",
    "cmakelists.txt": "cmake",
    "vagrantfile": "ruby",
    "gemfile": "ruby",
    "rakefile": "ruby",
    ".gitignore": "gitignore",
    ".dockerignore": "gitignore",
    ".env": "env",
    ".editorconfig": "editorconfig",
    ".prettierrc": "json",
    ".eslintrc": "json",
    "tsconfig.json": "json",
    "package.json": "json",
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _infer_language(filename: str) -> str | None:
    """Return a language identifier based on the file name / extension."""
    lower = filename.lower()

    # Check special filenames first
    if lower in _SPECIAL_FILE_LANGUAGE:
        return _SPECIAL_FILE_LANGUAGE[lower]

    # Extension-based lookup
    ext = Path(filename).suffix.lower()
    if ext in EXT_TO_LANGUAGE:
        return EXT_TO_LANGUAGE[ext]

    # Plain-text fallbacks by common extensionless names
    if lower in ("license", "license.txt", "license.md"):
        return "text"
    if lower in ("readme", "readme.txt", "readme.md"):
        return "markdown"
    if lower.startswith("dockerfile"):
        return "dockerfile"

    return None


def _is_binary(filename: str) -> bool:
    """Return True if the file extension indicates a binary format."""
    ext = Path(filename).suffix.lower()
    return ext in BINARY_EXTENSIONS


# ---------------------------------------------------------------------------
# FileBrowserHandler
# ---------------------------------------------------------------------------

class FileBrowserHandler:
    """Browse, read, write, and search files within a project root."""

    def __init__(self, cwd: str) -> None:
        self.cwd = Path(cwd).resolve()

    # ── internal helpers ──────────────────────────────────

    def _resolve(self, rel_path: str) -> Path:
        """Resolve *rel_path* against ``self.cwd`` and validate safety.

        Raises :class:`ValueError` if the resolved path escapes the project
        root, or if the path is absolute.
        """
        rel = Path(rel_path)

        # Reject absolute paths outright
        if rel.is_absolute():
            raise ValueError(f"Absolute paths are not allowed: {rel_path}")

        resolved = (self.cwd / rel).resolve()

        # Ensure the resolved path is inside cwd (or is cwd itself)
        try:
            resolved.relative_to(self.cwd)
        except ValueError:
            raise ValueError(
                f"Path '{rel_path}' resolves outside the project root"
            ) from None

        # On platforms that support os.readlink, also check symlinks.
        # If the resolved target itself is a symlink pointing outside,
        # resolve() already followed it — the relative_to check above
        # catches that case.

        return resolved

    # ── public API ────────────────────────────────────────

    def list_dir(self, rel_path: str | None = None) -> list[dict]:
        """List immediate children of a directory.

        Returns a list of dicts, each with keys:
        ``name``, ``path``, ``type``, ``size`` (files only), ``modified``.

        Directories are listed first, then files, both groups sorted
        alphabetically.  Hidden entries (starting with ``.``) are excluded.

        Raises :class:`FileNotFoundError` if the directory does not exist.
        """
        target = self.cwd if rel_path is None else self._resolve(rel_path)

        if not target.exists():
            raise FileNotFoundError(f"Directory not found: {rel_path}")
        if not target.is_dir():
            raise FileNotFoundError(f"Not a directory: {rel_path}")

        entries: list[dict] = []
        for child in target.iterdir():
            name = child.name
            # Skip hidden entries
            if name.startswith("."):
                continue

            rel = str(child.relative_to(self.cwd)).replace("\\", "/")
            mtime = datetime.fromtimestamp(
                child.stat().st_mtime, tz=timezone.utc
            ).isoformat()

            if child.is_dir():
                entries.append({
                    "name": name,
                    "path": rel,
                    "type": "dir",
                    "size": None,
                    "modified": mtime,
                })
            else:
                entries.append({
                    "name": name,
                    "path": rel,
                    "type": "file",
                    "size": child.stat().st_size,
                    "modified": mtime,
                })

        # Sort: directories first, then files; alphabetical within each group
        entries.sort(key=lambda e: (e["type"] != "dir", e["name"].lower()))
        return entries

    def read_file(self, rel_path: str) -> dict:
        """Read a text file and return its metadata.

        Returns a dict with keys: ``content``, ``language``, ``size``,
        ``modified``.

        Raises:
            FileNotFoundError: if the file does not exist.
            IsADirectoryError: if the path points to a directory.
            ValueError: if the file appears to be binary.
        """
        resolved = self._resolve(rel_path)

        if not resolved.exists():
            raise FileNotFoundError(f"File not found: {rel_path}")
        if resolved.is_dir():
            raise IsADirectoryError(f"Path is a directory: {rel_path}")
        if _is_binary(resolved.name):
            raise ValueError(f"Cannot read binary file: {rel_path}")

        stat_result = resolved.stat()
        content = resolved.read_text(encoding="utf-8")
        mtime = datetime.fromtimestamp(
            stat_result.st_mtime, tz=timezone.utc
        ).isoformat()

        return {
            "content": content,
            "language": _infer_language(resolved.name),
            "size": stat_result.st_size,
            "modified": mtime,
        }

    def write_file(self, rel_path: str, content: str) -> bool:
        """Write *content* to a file, creating parent directories if needed.

        Returns ``True`` on success.
        """
        resolved = self._resolve(rel_path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return True

    def search(self, query: str, max_results: int = 50) -> list[dict]:
        """Case-insensitive substring search by filename under the project root.

        Hidden entries (starting with ``.``) are excluded.
        Returns at most *max_results* results, each a dict with ``name``,
        ``path``, ``type``.
        """
        query_lower = query.lower()
        results: list[dict] = []

        for root, dirs, files in os.walk(self.cwd):
            # Skip hidden directories in-place
            dirs[:] = [d for d in dirs if not d.startswith(".")]

            root_path = Path(root)

            for name in files:
                if name.startswith("."):
                    continue
                if query_lower in name.lower():
                    full = root_path / name
                    rel = str(full.relative_to(self.cwd)).replace("\\", "/")
                    results.append({
                        "name": name,
                        "path": rel,
                        "type": "file",
                    })
                    if len(results) >= max_results:
                        return results

            # Also search directory names
            for name in dirs:
                if query_lower in name.lower():
                    full = root_path / name
                    rel = str(full.relative_to(self.cwd)).replace("\\", "/")
                    results.append({
                        "name": name,
                        "path": rel,
                        "type": "dir",
                    })
                    if len(results) >= max_results:
                        return results

        return results
