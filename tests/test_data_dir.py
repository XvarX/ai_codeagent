# tests/test_data_dir.py
import json
import tempfile
from pathlib import Path
from agentcore.data_dir import DataDir


def test_data_dir_creates_structure():
    """DataDir.init() should create all required subdirectories."""
    with tempfile.TemporaryDirectory() as tmp:
        dd = DataDir(Path(tmp) / ".ai-code-agent")
        dd.init()
        assert dd.root.exists()
        assert (dd.root / "logs" / "system").exists()
        assert (dd.root / "store" / "projects").exists()
        assert (dd.root / "mcp").exists()
        assert (dd.root / "skills").exists()


def test_project_hash():
    """project_hash should return first 16 hex chars of SHA256."""
    dd = DataDir(Path("/fake"))
    h = dd.project_hash(r"D:\space\myproject")
    assert len(h) == 16
    # Same path → same hash
    assert dd.project_hash(r"D:\space\myproject") == h


def test_project_dir():
    """project_dir returns the hashed directory under store/projects/."""
    with tempfile.TemporaryDirectory() as tmp:
        dd = DataDir(Path(tmp) / ".ai-code-agent")
        pdir = dd.project_dir(r"D:\space\myproject")
        assert pdir.parent == dd.root / "store" / "projects"
        assert pdir.name == dd.project_hash(r"D:\space\myproject")


def test_session_dir():
    """session_dir returns the session directory under a project."""
    with tempfile.TemporaryDirectory() as tmp:
        dd = DataDir(Path(tmp) / ".ai-code-agent")
        sdir = dd.session_dir(r"D:\space\myproject", "test-session-id")
        assert "test-session-id" in str(sdir)
        assert "sessions" in str(sdir)


def test_projects_index_path():
    """projects_index returns the path to projects.json."""
    dd = DataDir(Path("/fake"))
    assert dd.projects_index_path == dd.root / "store" / "projects.json"


def test_config_path():
    """config_path returns the path to config.yaml."""
    dd = DataDir(Path("/fake"))
    assert dd.config_path == dd.root / "config.yaml"
