# agentcore/session_store.py
"""Project and session CRUD — manages store/projects/ directory tree.

Directory structure:
    sessions/{session_id}/
    ├── meta.json           ← session metadata
    └── agents/
        ├── 1/
        │   ├── meta.json   ← agent metadata
        │   ├── messages.json
        │   ├── debug_log.json
        │   └── llm_log.json
        ├── 2/
        └── ...
"""

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

        meta_path = self._dd.project_meta_path(project_path)
        meta = {"path": project_path, "name": display_name, "last_opened": now}
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        index_path = self._dd.projects_index_path
        index = []
        if index_path.exists():
            index = json.loads(index_path.read_text(encoding="utf-8"))
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
        self.register_project(project_path)

    def delete_project(self, project_path: str):
        import shutil
        pdir = self._dd.project_dir(project_path)
        if pdir.exists():
            shutil.rmtree(pdir, ignore_errors=True)
        index_path = self._dd.projects_index_path
        if index_path.exists():
            index = json.loads(index_path.read_text(encoding="utf-8"))
            index = [p for p in index if p.get("path") != project_path]
            index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── Sessions ────────────────────────────────────

    def create_session(self, project_path: str, title: str = "New Chat") -> str:
        """Create a new session with initial agent directory, return session ID."""
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
        (sdir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        # Create initial agent directory (id=1)
        self._init_agent_dir(project_path, session_id, "1")

        return session_id

    def _init_agent_dir(self, project_path: str, session_id: str, agent_id: str):
        """Initialize an agent directory with empty data files."""
        adir = self._dd.agent_dir(project_path, session_id, agent_id)
        adir.mkdir(parents=True, exist_ok=True)
        (adir / "messages.json").write_text("[]", encoding="utf-8")
        (adir / "llm_log.json").write_text("[]", encoding="utf-8")
        (adir / "debug_log.json").write_text("[]", encoding="utf-8")

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
                    result.append(json.loads(meta_path.read_text(encoding="utf-8")))
        result.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
        return result

    def get_session_meta(self, project_path: str, session_id: str) -> dict | None:
        meta_path = self._dd.session_meta_path(project_path, session_id)
        if not meta_path.exists():
            return None
        return json.loads(meta_path.read_text(encoding="utf-8"))

    def update_session_meta(self, project_path: str, session_id: str, **fields):
        meta_path = self._dd.session_meta_path(project_path, session_id)
        if not meta_path.exists():
            return
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta.update(fields)
        meta["updated_at"] = datetime.now(timezone.utc).isoformat()
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def delete_session(self, project_path: str, session_id: str):
        import shutil
        sdir = self._dd.session_dir(project_path, session_id)
        if sdir.exists():
            shutil.rmtree(sdir, ignore_errors=True)

    # ── Agent-level operations ─────────────────────

    def list_agents(self, project_path: str, session_id: str) -> list[str]:
        """Return agent IDs by scanning agents/ directory."""
        agents_dir = self._dd.session_dir(project_path, session_id) / "agents"
        if not agents_dir.exists():
            return []
        return sorted(
            [d.name for d in agents_dir.iterdir() if d.is_dir()],
            key=lambda x: int(x) if x.isdigit() else 999,
        )

    # ── Messages (per agent) ───────────────────────

    def append_message(self, project_path: str, session_id: str,
                       agent_id: str, message: dict):
        adir = self._dd.agent_dir(project_path, session_id, agent_id)
        adir.mkdir(parents=True, exist_ok=True)
        msgs_path = adir / "messages.json"
        msgs = json.loads(msgs_path.read_text(encoding="utf-8")) if msgs_path.exists() else []
        msgs.append(message)
        msgs_path.write_text(json.dumps(msgs, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_messages(self, project_path: str, session_id: str,
                      agent_id: str = "1") -> list[dict]:
        msgs_path = self._dd.agent_dir(project_path, session_id, agent_id) / "messages.json"
        if not msgs_path.exists():
            return []
        return json.loads(msgs_path.read_text(encoding="utf-8"))

    def overwrite_messages(self, project_path: str, session_id: str,
                           agent_id: str, messages: list[dict]):
        adir = self._dd.agent_dir(project_path, session_id, agent_id)
        adir.mkdir(parents=True, exist_ok=True)
        (adir / "messages.json").write_text(
            json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8")
        self.update_session_meta(project_path, session_id, msg_count=len(messages))

    # ── Agent metadata ─────────────────────────────

    def save_agent_meta(self, project_path: str, session_id: str,
                        agent_id: str, meta: dict):
        adir = self._dd.agent_dir(project_path, session_id, agent_id)
        adir.mkdir(parents=True, exist_ok=True)
        (adir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_agent_meta(self, project_path: str, session_id: str,
                        agent_id: str) -> dict | None:
        meta_path = self._dd.agent_dir(project_path, session_id, agent_id) / "meta.json"
        if not meta_path.exists():
            return None
        return json.loads(meta_path.read_text(encoding="utf-8"))

    # ── Debug log (per agent) ──────────────────────

    def save_agent_debug_log(self, project_path: str, session_id: str,
                             agent_id: str, entries: list[dict]):
        adir = self._dd.agent_dir(project_path, session_id, agent_id)
        adir.mkdir(parents=True, exist_ok=True)
        (adir / "debug_log.json").write_text(
            json.dumps(entries, ensure_ascii=False), encoding="utf-8")

    def load_agent_debug_log(self, project_path: str, session_id: str,
                             agent_id: str = "1") -> list[dict]:
        log_path = self._dd.agent_dir(project_path, session_id, agent_id) / "debug_log.json"
        if not log_path.exists():
            return []
        return json.loads(log_path.read_text(encoding="utf-8"))

    def append_debug_entry(self, project_path: str, session_id: str,
                           agent_id: str, entry: dict):
        adir = self._dd.agent_dir(project_path, session_id, agent_id)
        adir.mkdir(parents=True, exist_ok=True)
        log_path = adir / "debug_log.json"
        logs = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []
        logs.append(entry)
        log_path.write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── LLM log (per agent) ────────────────────────

    def append_llm_log(self, project_path: str, session_id: str,
                       agent_id: str, entry: dict):
        adir = self._dd.agent_dir(project_path, session_id, agent_id)
        adir.mkdir(parents=True, exist_ok=True)
        log_path = adir / "llm_log.json"
        logs = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []
        logs.append(entry)
        log_path.write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── Backward-compat aliases (delegate to unified methods) ──

    def save_subagent_meta(self, project_path: str, session_id: str,
                           sub_id: str, meta: dict):
        self.save_agent_meta(project_path, session_id, sub_id, meta)

    def save_subagent_debug_log(self, project_path: str, session_id: str,
                                sub_id: str, entries: list[dict]):
        self.save_agent_debug_log(project_path, session_id, sub_id, entries)

    def load_subagent_meta(self, project_path: str, session_id: str,
                           sub_id: str) -> dict | None:
        return self.load_agent_meta(project_path, session_id, sub_id)

    def list_subagents(self, project_path: str, session_id: str) -> list[dict]:
        agents = self.list_agents(project_path, session_id)
        result = []
        for aid in agents:
            if aid == "1":
                continue
            meta = self.load_agent_meta(project_path, session_id, aid)
            if meta:
                result.append(meta)
        return result

    def append_subagent_message(self, project_path: str, session_id: str,
                                sub_id: str, message: dict):
        self.append_message(project_path, session_id, sub_id, message)

    def append_subagent_llm_log(self, project_path: str, session_id: str,
                                sub_id: str, entry: dict):
        self.append_llm_log(project_path, session_id, sub_id, entry)

    def load_debug_log(self, project_path: str, session_id: str) -> list[dict]:
        """Backward compat: load debug log for initial agent."""
        return self.load_agent_debug_log(project_path, session_id, "1")
