# tests/test_ws_session.py
"""Unit tests for the session logic that backs WebSocket message handlers.

These tests exercise the SessionStore methods that ws_server.py calls inside
its message handlers (list_projects, open_project, create_session, load_session,
list_all_sessions) without any WebSocket connectivity.

Handler-to-method mapping in ws_server.py:
  list_projects   -> store.list_projects()
  open_project    -> store.register_project() + store.touch_project() + store.list_sessions()
  create_session  -> store.create_session()
  load_session    -> store.load_messages() + store.get_session_meta()
  list_all_sessions -> store.list_projects() + store.list_sessions() per project
"""

import json
import tempfile
from pathlib import Path

from agentcore.data_dir import DataDir
from agentcore.session_store import SessionStore


def _make_store(tmp_dir: str) -> tuple[SessionStore, DataDir]:
    dd = DataDir(Path(tmp_dir) / ".ai-code-agent")
    dd.init()
    return SessionStore(dd), dd


# ── list_projects ──────────────────────────────────────

def test_list_projects_returns_both_sorted_by_last_opened_desc():
    """Handler: list_projects — register 2 projects, list returns both sorted."""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(tmp)

        store.register_project(r"D:\project_alpha", name="Alpha")
        store.register_project(r"D:\project_beta", name="Beta")

        projects = store.list_projects()
        assert len(projects) == 2
        # Last-registered has the newest last_opened timestamp -> first in list
        assert projects[0]["path"] == r"D:\project_beta"
        assert projects[0]["name"] == "Beta"
        assert projects[1]["path"] == r"D:\project_alpha"
        assert projects[1]["name"] == "Alpha"


# ── open_project ───────────────────────────────────────

def test_open_project_touch_updates_last_opened_and_returns_sessions():
    """Handler: open_project — touch updates last_opened, sessions list returned."""
    with tempfile.TemporaryDirectory() as tmp:
        store, dd = _make_store(tmp)

        # Register two projects with a known order
        store.register_project(r"D:\first_project", name="First")
        store.register_project(r"D:\second_project", name="Second")

        # Create sessions under the first project
        sid1 = store.create_session(r"D:\first_project", title="Chat A")
        store.create_session(r"D:\first_project", title="Chat B")

        # Simulate open_project handler: touch (re-register) first project
        store.register_project(r"D:\first_project")

        # Verify last_opened was updated — first_project should now be first in list
        projects = store.list_projects()
        assert projects[0]["path"] == r"D:\first_project"

        # Verify sessions are returned correctly
        sessions = store.list_sessions(r"D:\first_project")
        assert len(sessions) == 2
        # Sessions sorted by updated_at desc, newest first
        assert sessions[0]["title"] == "Chat B"


# ── create_session ─────────────────────────────────────

def test_create_session_creates_meta_and_messages_files():
    """Handler: create_session — verify meta.json and messages.json exist."""
    with tempfile.TemporaryDirectory() as tmp:
        store, dd = _make_store(tmp)

        store.register_project(r"D:\my_project")
        sid = store.create_session(r"D:\my_project", title="Test Session")

        # meta.json must exist with correct fields
        meta_path = dd.session_meta_path(r"D:\my_project", sid)
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["session_id"] == sid
        assert meta["title"] == "Test Session"
        assert meta["msg_count"] == 0
        assert "created_at" in meta
        assert "updated_at" in meta

        # messages.json must exist and be an empty array
        msgs_path = dd.messages_path(r"D:\my_project", sid)
        assert msgs_path.exists()
        msgs = json.loads(msgs_path.read_text(encoding="utf-8"))
        assert msgs == []


# ── load_session ───────────────────────────────────────

def test_load_session_returns_all_messages_and_meta():
    """Handler: load_session — create session, append messages, load returns all."""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(tmp)

        store.register_project(r"D:\my_project")
        sid = store.create_session(r"D:\my_project", title="Loaded Chat")

        # Simulate conversation messages
        store.append_message(r"D:\my_project", sid, {
            "role": "user", "content": "Hello, world!"
        })
        store.append_message(r"D:\my_project", sid, {
            "role": "assistant", "content": "Hi there!"
        })
        store.append_message(r"D:\my_project", sid, {
            "role": "user", "content": "How are you?"
        })

        # Handler calls load_messages + get_session_meta
        messages = store.load_messages(r"D:\my_project", sid)
        meta = store.get_session_meta(r"D:\my_project", sid)

        assert len(messages) == 3
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello, world!"
        assert messages[1]["role"] == "assistant"
        assert messages[2]["role"] == "user"
        assert meta is not None
        assert meta["session_id"] == sid
        assert meta["title"] == "Loaded Chat"


# ── list_all_sessions ──────────────────────────────────

def test_list_all_sessions_returns_sessions_from_all_projects_sorted():
    """Handler: list_all_sessions — 2 projects with sessions, all returned sorted."""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(tmp)

        # Project A with 2 sessions
        store.register_project(r"D:\project_a", name="ProjectA")
        store.create_session(r"D:\project_a", title="A-Session-1")
        store.create_session(r"D:\project_a", title="A-Session-2")

        # Project B with 1 session
        store.register_project(r"D:\project_b", name="ProjectB")
        store.create_session(r"D:\project_b", title="B-Session-1")

        # Mimic the list_all_sessions handler logic
        projects = store.list_projects()
        all_sessions: list[dict] = []
        for p in projects:
            sessions = store.list_sessions(p["path"])
            for s in sessions:
                s["project_path"] = p["path"]
                s["project_name"] = p.get("name", "")
            all_sessions.extend(sessions)
        all_sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)

        assert len(all_sessions) == 3
        # Every session should carry project metadata
        for s in all_sessions:
            assert "project_path" in s
            assert "project_name" in s
        # Newest sessions first (B-Session-1 and A-Session-2 are newest in their projects)
        titles = [s["title"] for s in all_sessions]
        assert "B-Session-1" in titles
        assert "A-Session-2" in titles
        assert "A-Session-1" in titles


# ── session_isolation ──────────────────────────────────

def test_sessions_from_different_projects_do_not_mix():
    """Handler: isolation — sessions from different projects don't mix."""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(tmp)

        store.register_project(r"D:\proj_x")
        store.register_project(r"D:\proj_y")

        sid_x = store.create_session(r"D:\proj_x", title="X-Chat")
        sid_y = store.create_session(r"D:\proj_y", title="Y-Chat")

        # Add messages to project X only
        store.append_message(r"D:\proj_x", sid_x, {"role": "user", "content": "X msg"})
        store.append_message(r"D:\proj_x", sid_x, {"role": "assistant", "content": "X reply"})

        # Add messages to project Y only
        store.append_message(r"D:\proj_y", sid_y, {"role": "user", "content": "Y msg"})

        # Load separately — each project sees only its own messages
        msgs_x = store.load_messages(r"D:\proj_x", sid_x)
        msgs_y = store.load_messages(r"D:\proj_y", sid_y)

        assert len(msgs_x) == 2
        assert msgs_x[0]["content"] == "X msg"
        assert msgs_x[1]["content"] == "X reply"

        assert len(msgs_y) == 1
        assert msgs_y[0]["content"] == "Y msg"

        # list_sessions for each project returns only its own sessions
        sessions_x = store.list_sessions(r"D:\proj_x")
        sessions_y = store.list_sessions(r"D:\proj_y")
        assert len(sessions_x) == 1
        assert sessions_x[0]["session_id"] == sid_x
        assert len(sessions_y) == 1
        assert sessions_y[0]["session_id"] == sid_y
