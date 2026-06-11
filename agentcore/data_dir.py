# agentcore/data_dir.py
"""Unified data directory — single entry point for all paths."""

import hashlib
from pathlib import Path


class DataDir:
    """Manages the .ai-code-agent/ data directory structure.

    Usage:
        dd = DataDir(Path.home() / ".ai-code-agent")   # packaged mode
        dd = DataDir(project_root / ".ai-code-agent")   # dev mode
        dd.init()  # create directories if missing
    """

    def __init__(self, root: Path):
        self.root = root

    def init(self):
        """Create the full directory tree."""
        dirs = [
            self.root / "logs" / "system",
            self.root / "store" / "projects",
            self.root / "mcp",
            self.root / "skills",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    # ── Path accessors ──────────────────────────────

    @property
    def config_path(self) -> Path:
        return self.root / "config.yaml"

    @property
    def local_config_path(self) -> Path:
        return self.root / "config.local.json"

    @property
    def projects_index_path(self) -> Path:
        return self.root / "store" / "projects.json"

    def system_log_dir(self) -> Path:
        return self.root / "logs" / "system"

    def mcp_dir(self) -> Path:
        return self.root / "mcp"

    def skills_dir(self) -> Path:
        return self.root / "skills"

    # ── Project / Session paths ─────────────────────

    @staticmethod
    def project_hash(project_path: str) -> str:
        """SHA256 of the normalized project path, first 16 hex chars."""
        normalized = Path(project_path).resolve().as_posix().lower()
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def project_dir(self, project_path: str) -> Path:
        """Return the hashed project directory."""
        return self.root / "store" / "projects" / self.project_hash(project_path)

    def project_meta_path(self, project_path: str) -> Path:
        return self.project_dir(project_path) / "meta.json"

    def sessions_dir(self, project_path: str) -> Path:
        return self.project_dir(project_path) / "sessions"

    def session_dir(self, project_path: str, session_id: str) -> Path:
        return self.sessions_dir(project_path) / session_id

    def session_meta_path(self, project_path: str, session_id: str) -> Path:
        return self.session_dir(project_path, session_id) / "meta.json"

    def messages_path(self, project_path: str, session_id: str) -> Path:
        return self.session_dir(project_path, session_id) / "messages.json"

    def llm_log_path(self, project_path: str, session_id: str) -> Path:
        return self.session_dir(project_path, session_id) / "llm_log.json"

    def debug_log_path(self, project_path: str, session_id: str) -> Path:
        return self.session_dir(project_path, session_id) / "debug_log.json"

    def agent_dir(self, project_path: str, session_id: str, agent_id: str) -> Path:
        """Return the directory for a specific agent within a session."""
        return self.session_dir(project_path, session_id) / "agents" / agent_id

    def subagent_dir(self, project_path: str, session_id: str, sub_id: str) -> Path:
        """Alias for agent_dir (backward compat)."""
        return self.agent_dir(project_path, session_id, sub_id)

    # ── Project-level .myagent paths ─────────────────

    @staticmethod
    def project_myagent_dir(project_path: str) -> Path:
        """Return the .myagent/ directory for a given project."""
        return Path(project_path).resolve() / ".myagent"
