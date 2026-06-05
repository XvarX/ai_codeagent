# agentcore/session_store.py
"""Project and session CRUD — manages store/projects/ directory tree."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from agentcore.data_dir import DataDir


class SessionStore:
    """Create, list, read, and update projects and sessions."""

    def __init__(self, data_dir: DataDir):
        self._dd = data_dir

    # ── Projects ────────────────────────────────────

    def register_project(self, project_path: str, name: str = ""):
        """Create project dir + meta.json, update projects.json index."""
        pdir = self._dd.project_dir(project_path)
        pdir.mkdir(parents=True, exist_ok=True)
        sessions_dir = self._dd.sessions_dir(project_path)
        sessions_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc).isoformat()
        display_name = name or Path(project_path).name

        # Write meta.json
        meta_path = self._dd.project_meta_path(project_path)
        meta = {"path": project_path, "name": display_name, "last_opened": now}
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        # Update projects.json index
        index_path = self._dd.projects_index_path
        index = []
        if index_path.exists():
            index = json.loads(index_path.read_text(encoding="utf-8"))
        # Remove existing entry for this path
        index = [p for p in index if p.get("path") != project_path]
        index.append({
            "hash": DataDir.project_hash(project_path),
            "path": project_path,
            "name": display_name,
            "last_opened": now,
        })
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_projects(self) -> list[dict]:
        """Return projects sorted by last_opened descending."""
        index_path = self._dd.projects_index_path
        if not index_path.exists():
            return []
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index.sort(key=lambda p: p.get("last_opened", ""), reverse=True)
        return index

    def touch_project(self, project_path: str):
        """Update last_opened timestamp for a project."""
        self.register_project(project_path)

    # ── Sessions ────────────────────────────────────

    def create_session(self, project_path: str, title: str = "New Chat") -> str:
        """Create a new session, return its ID."""
        session_id = str(uuid.uuid4())
        sdir = self._dd.session_dir(project_path, session_id)
        sdir.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc).isoformat()
        meta = {
            "session_id": session_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "model": "",
            "msg_count": 0,
        }
        meta_path = self._dd.session_meta_path(project_path, session_id)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        # Init empty messages and llm_log
        msgs_path = self._dd.messages_path(project_path, session_id)
        msgs_path.write_text("[]", encoding="utf-8")
        log_path = self._dd.llm_log_path(project_path, session_id)
        log_path.write_text("[]", encoding="utf-8")

        return session_id

    def list_sessions(self, project_path: str) -> list[dict]:
        """Return sessions for a project, sorted by updated_at descending."""
        sessions_dir = self._dd.sessions_dir(project_path)
        if not sessions_dir.exists():
            return []
        result = []
        for sdir in sessions_dir.iterdir():
            if sdir.is_dir():
                meta_path = sdir / "meta.json"
                if meta_path.exists():
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    result.append(meta)
        result.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
        return result

    def get_session_meta(self, project_path: str, session_id: str) -> dict | None:
        meta_path = self._dd.session_meta_path(project_path, session_id)
        if not meta_path.exists():
            return None
        return json.loads(meta_path.read_text(encoding="utf-8"))

    def update_session_meta(self, project_path: str, session_id: str, **fields):
        """Update fields in session meta.json."""
        meta_path = self._dd.session_meta_path(project_path, session_id)
        if not meta_path.exists():
            return
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta.update(fields)
        meta["updated_at"] = datetime.now(timezone.utc).isoformat()
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── Messages ────────────────────────────────────

    def append_message(self, project_path: str, session_id: str, message: dict):
        """Append a single message to messages.json (append-only)."""
        msgs_path = self._dd.messages_path(project_path, session_id)
        msgs_path.parent.mkdir(parents=True, exist_ok=True)
        if msgs_path.exists():
            msgs = json.loads(msgs_path.read_text(encoding="utf-8"))
        else:
            msgs = []
        msgs.append(message)
        msgs_path.write_text(json.dumps(msgs, ensure_ascii=False, indent=2), encoding="utf-8")

    def append_messages(self, project_path: str, session_id: str, messages: list[dict]):
        """Append multiple messages at once."""
        for m in messages:
            self.append_message(project_path, session_id, m)

    def load_messages(self, project_path: str, session_id: str) -> list[dict]:
        """Load all messages for a session."""
        msgs_path = self._dd.messages_path(project_path, session_id)
        if not msgs_path.exists():
            return []
        return json.loads(msgs_path.read_text(encoding="utf-8"))

    def overwrite_messages(self, project_path: str, session_id: str, messages: list[dict]):
        """Replace all messages (used after compaction)."""
        msgs_path = self._dd.messages_path(project_path, session_id)
        msgs_path.write_text(json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")
        self.update_session_meta(project_path, session_id, msg_count=len(messages))

    # ── LLM Log ─────────────────────────────────────

    def append_llm_log(self, project_path: str, session_id: str, entry: dict):
        """Append an LLM request/response log entry."""
        log_path = self._dd.llm_log_path(project_path, session_id)
        if log_path.exists():
            logs = json.loads(log_path.read_text(encoding="utf-8"))
        else:
            logs = []
        logs.append(entry)
        log_path.write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── Subagents ───────────────────────────────────

    def append_subagent_message(self, project_path: str, session_id: str,
                                 sub_id: str, message: dict):
        sdir = self._dd.subagent_dir(project_path, session_id, sub_id)
        sdir.mkdir(parents=True, exist_ok=True)
        msgs_path = sdir / "messages.json"
        if msgs_path.exists():
            msgs = json.loads(msgs_path.read_text(encoding="utf-8"))
        else:
            msgs = []
        msgs.append(message)
        msgs_path.write_text(json.dumps(msgs, ensure_ascii=False, indent=2), encoding="utf-8")

    def append_subagent_llm_log(self, project_path: str, session_id: str,
                                 sub_id: str, entry: dict):
        sdir = self._dd.subagent_dir(project_path, session_id, sub_id)
        sdir.mkdir(parents=True, exist_ok=True)
        log_path = sdir / "llm_log.json"
        if log_path.exists():
            logs = json.loads(log_path.read_text(encoding="utf-8"))
        else:
            logs = []
        logs.append(entry)
        log_path.write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8")
