# tests/test_session_store.py
import json
import tempfile
from pathlib import Path
from agentcore.data_dir import DataDir
from agentcore.session_store import SessionStore


def _make_store(tmp_dir: str) -> tuple[SessionStore, DataDir]:
    dd = DataDir(Path(tmp_dir) / ".ai-code-agent")
    dd.init()
    return SessionStore(dd), dd


def test_register_project():
    """register_project creates project dir and updates index."""
    with tempfile.TemporaryDirectory() as tmp:
        store, dd = _make_store(tmp)
        store.register_project(r"D:\space\myproject")
        assert dd.project_dir(r"D:\space\myproject").exists()
        meta = json.loads((dd.project_meta_path(r"D:\space\myproject")).read_text())
        assert meta["path"] == r"D:\space\myproject"
        idx = json.loads(dd.projects_index_path.read_text())
        assert len(idx) == 1
        assert idx[0]["path"] == r"D:\space\myproject"


def test_list_projects():
    """list_projects returns projects sorted by last_opened desc."""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(tmp)
        store.register_project(r"D:\project_a")
        store.register_project(r"D:\project_b")
        projects = store.list_projects()
        assert len(projects) == 2
        assert projects[0]["path"] == r"D:\project_b"


def test_create_session():
    """create_session creates session dir with meta.json."""
    with tempfile.TemporaryDirectory() as tmp:
        store, dd = _make_store(tmp)
        store.register_project(r"D:\space\myproject")
        sid = store.create_session(r"D:\space\myproject", title="Test Chat")
        assert sid
        meta_path = dd.session_meta_path(r"D:\space\myproject", sid)
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["title"] == "Test Chat"


def test_list_sessions():
    """list_sessions returns sessions for a project."""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(tmp)
        store.register_project(r"D:\space\myproject")
        store.create_session(r"D:\space\myproject", title="First")
        s2 = store.create_session(r"D:\space\myproject", title="Second")
        sessions = store.list_sessions(r"D:\space\myproject")
        assert len(sessions) == 2
        assert sessions[0]["session_id"] == s2


def test_append_message():
    """append_message writes a message to messages.json."""
    with tempfile.TemporaryDirectory() as tmp:
        store, dd = _make_store(tmp)
        store.register_project(r"D:\space\myproject")
        sid = store.create_session(r"D:\space\myproject")
        store.append_message(r"D:\space\myproject", sid, {
            "role": "user", "content": "Hello"
        })
        msgs = json.loads(dd.messages_path(r"D:\space\myproject", sid).read_text())
        assert len(msgs) == 1
        assert msgs[0]["content"] == "Hello"


def test_load_messages():
    """load_messages returns stored messages."""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(tmp)
        store.register_project(r"D:\space\myproject")
        sid = store.create_session(r"D:\space\myproject")
        store.append_message(r"D:\space\myproject", sid, {"role": "user", "content": "Hi"})
        store.append_message(r"D:\space\myproject", sid, {"role": "assistant", "content": "Hey"})
        msgs = store.load_messages(r"D:\space\myproject", sid)
        assert len(msgs) == 2
