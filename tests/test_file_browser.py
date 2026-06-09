# tests/test_file_browser.py
"""Unit tests for FileBrowserHandler — list_dir, read_file, write_file, search,
and path-safety enforcement."""

import os
import tempfile
from pathlib import Path

import pytest

from agentcore.file_browser import FileBrowserHandler


# ── helpers ───────────────────────────────────────────────

@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """Create a small fake project tree and return its root."""
    # directories
    (tmp_path / "src").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / ".hidden_dir").mkdir()          # should be skipped

    # files
    (tmp_path / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
    (tmp_path / "src" / "utils.ts").write_text("export const x = 1;", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Hello", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("*.pyc\n", encoding="utf-8")  # hidden, skipped
    (tmp_path / "docs" / "guide.md").write_text("Guide content", encoding="utf-8")
    # binary file
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return tmp_path


@pytest.fixture()
def handler(project: Path) -> FileBrowserHandler:
    return FileBrowserHandler(str(project))


# ── TestListDir ───────────────────────────────────────────

class TestListDir:
    def test_list_root(self, handler: FileBrowserHandler, project: Path):
        entries = handler.list_dir(None)
        names = [e["name"] for e in entries]
        # .gitignore and .hidden_dir should be hidden
        assert ".gitignore" not in names
        assert ".hidden_dir" not in names
        # visible items present
        assert "docs" in names
        assert "src" in names
        assert "README.md" in names
        assert "logo.png" in names
        # dirs first, then files, alphabetical within group
        types = [e["type"] for e in entries]
        first_file_idx = next(i for i, t in enumerate(types) if t == "file")
        assert all(t == "dir" for t in types[:first_file_idx])
        assert all(t == "file" for t in types[first_file_idx:])

    def test_list_subdir(self, handler: FileBrowserHandler, project: Path):
        entries = handler.list_dir("src")
        names = [e["name"] for e in entries]
        assert "main.py" in names
        assert "utils.ts" in names

    def test_entry_types(self, handler: FileBrowserHandler, project: Path):
        entries = handler.list_dir(None)
        entry_map = {e["name"]: e for e in entries}
        # directory entry
        docs = entry_map["docs"]
        assert docs["type"] == "dir"
        assert "size" not in docs or docs.get("size") is None
        assert docs["path"] == "docs"
        # file entry
        readme = entry_map["README.md"]
        assert readme["type"] == "file"
        assert readme["size"] > 0
        assert readme["path"] == "README.md"

    def test_nonexistent_dir(self, handler: FileBrowserHandler):
        with pytest.raises(FileNotFoundError):
            handler.list_dir("no_such_dir")


# ── TestReadFile ──────────────────────────────────────────

class TestReadFile:
    def test_read_text_file(self, handler: FileBrowserHandler, project: Path):
        result = handler.read_file("src/main.py")
        assert "print('hello')" in result["content"]
        assert result["language"] == "python"
        assert result["size"] > 0
        assert "modified" in result

    def test_read_binary_file(self, handler: FileBrowserHandler, project: Path):
        with pytest.raises(ValueError, match="[Bb]inary"):
            handler.read_file("logo.png")

    def test_read_nonexistent_file(self, handler: FileBrowserHandler):
        with pytest.raises(FileNotFoundError):
            handler.read_file("does_not_exist.py")

    def test_read_directory_raises(self, handler: FileBrowserHandler):
        with pytest.raises(IsADirectoryError):
            handler.read_file("src")


# ── TestWriteFile ─────────────────────────────────────────

class TestWriteFile:
    def test_write_new_content(self, handler: FileBrowserHandler, project: Path):
        result = handler.write_file("src/new_file.py", "# new")
        assert result is True
        assert (project / "src" / "new_file.py").read_text(encoding="utf-8") == "# new"

    def test_write_creates_parent_dirs(self, handler: FileBrowserHandler, project: Path):
        result = handler.write_file("deep/nested/dir/file.txt", "hello")
        assert result is True
        assert (project / "deep" / "nested" / "dir" / "file.txt").read_text(
            encoding="utf-8"
        ) == "hello"


# ── TestSearch ────────────────────────────────────────────

class TestSearch:
    def test_search_by_name(self, handler: FileBrowserHandler):
        results = handler.search("main")
        names = [r["name"] for r in results]
        assert "main.py" in names
        # each result has required keys
        for r in results:
            assert "name" in r
            assert "path" in r
            assert "type" in r

    def test_search_case_insensitive(self, handler: FileBrowserHandler):
        results = handler.search("README")
        assert len(results) >= 1
        assert results[0]["name"] == "README.md"

    def test_search_no_results(self, handler: FileBrowserHandler):
        results = handler.search("zzz_nonexistent_file")
        assert results == []


# ── TestPathSafety ────────────────────────────────────────

class TestPathSafety:
    def test_reject_path_traversal(self, handler: FileBrowserHandler):
        with pytest.raises(ValueError, match="[Oo]utside|[Ee]scape|[Ii]nvalid"):
            handler.list_dir("../../etc")

    def test_reject_absolute_path(self, handler: FileBrowserHandler):
        with pytest.raises(ValueError, match="[Oo]utside|[Ee]scape|[Aa]bsolute|[Ii]nvalid"):
            handler.read_file("C:/Windows/System32/drivers/etc/hosts")

    def test_reject_symlink_escape(self, handler: FileBrowserHandler, project: Path):
        # create a symlink pointing outside the project
        outside = project.parent / "outside_target.txt"
        outside.write_text("secret", encoding="utf-8")
        link = project / "escape_link"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("Platform does not support symlinks")
        with pytest.raises(ValueError, match="[Oo]utside|[Ee]scape|[Ii]nvalid"):
            handler.read_file("escape_link")
        # cleanup
        outside.unlink(missing_ok=True)
