# 统一数据目录实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 `.ai-code-agent/` 统一数据目录，支持配置、日志、多对话持久化，开发/打包模式统一。

**Architecture:** 新增 `DataDir` 类作为所有路径操作的唯一入口。Tauri 通过 `--data-dir` 传路径，Python 只用这个路径。session 按项目分组，每个 session 独立目录存放对话历史和 LLM 日志。

**Tech Stack:** Python 3 (pathlib, hashlib, json, uuid), Rust/Tauri (app.path()), WebSocket 消息协议

---

## File Structure

| 操作 | 文件 | 职责 |
|---|---|---|
| Create | `agentcore/data_dir.py` | `DataDir` 类——所有路径计算和目录创建的唯一入口 |
| Modify | `agentcore/config.py` | 从 `data_dir` 读 config.yaml，支持两级配置加载 |
| Modify | `agentcore/main.py` | 解析 `--data-dir` 参数，传给 config 和 ws_server |
| Modify | `agentcore/ws_server.py` | 新增 session/project 相关 WebSocket 消息处理 |
| Modify | `agentcore/agent.py` | Agent 持有 session_id 和 DataDir，实时持久化消息 |
| Modify | `ui/src-tauri/src/main.rs` | 打包/开发模式传 `--data-dir` |
| Modify | `.gitignore` | 加 `.ai-code-agent/` |
| Create | `tests/test_data_dir.py` | DataDir 单元测试 |
| Create | `tests/test_session_store.py` | session 存储测试 |
| Create | `ui/src/stores/session.ts` | Pinia store — 项目/session 状态管理 |
| Create | `ui/src/components/ProjectPicker.vue` | 项目选择对话框 |
| Create | `ui/src/components/SessionList.vue` | session 列表 + 切换/新建组件 |
| Modify | `ui/src/App.vue` | 集成项目选择和 session 管理 |
| Modify | `ui/src/services/agentWs.ts` | 新增 session 相关 WebSocket 事件监听 |

---

### Task 1: DataDir 核心类

**Files:**
- Create: `agentcore/data_dir.py`
- Create: `tests/test_data_dir.py`

- [ ] **Step 1: 写 DataDir 测试**

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_data_dir.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agentcore.data_dir'`

- [ ] **Step 3: 实现 DataDir 类**

```python
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

    def subagent_dir(self, project_path: str, session_id: str, sub_id: str) -> Path:
        return self.session_dir(project_path, session_id) / "subagents" / sub_id

    # ── Project-level .myagent paths ─────────────────

    @staticmethod
    def project_myagent_dir(project_path: str) -> Path:
        """Return the .myagent/ directory for a given project."""
        return Path(project_path).resolve() / ".myagent"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_data_dir.py -v`
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add agentcore/data_dir.py tests/test_data_dir.py
git commit -m "feat: add DataDir class — unified path management for .ai-code-agent/"
```

---

### Task 2: SessionStore — session 和 project 的 CRUD

**Files:**
- Create: `agentcore/session_store.py`
- Create: `tests/test_session_store.py`

- [ ] **Step 1: 写 SessionStore 测试**

```python
# tests/test_session_store.py
import json
import tempfile
from datetime import datetime
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
        # Project dir exists
        assert dd.project_dir(r"D:\space\myproject").exists()
        # meta.json written
        meta = json.loads((dd.project_meta_path(r"D:\space\myproject")).read_text())
        assert meta["path"] == r"D:\space\myproject"
        # projects.json updated
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
        # Most recently opened first
        assert projects[0]["path"] == r"D:\project_b"


def test_create_session():
    """create_session creates session dir with meta.json."""
    with tempfile.TemporaryDirectory() as tmp:
        store, dd = _make_store(tmp)
        store.register_project(r"D:\space\myproject")
        sid = store.create_session(r"D:\space\myproject", title="Test Chat")
        assert sid  # non-empty string
        meta_path = dd.session_meta_path(r"D:\space\myproject", sid)
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["title"] == "Test Chat"


def test_list_sessions():
    """list_sessions returns sessions for a project."""
    with tempfile.TemporaryDirectory() as tmp:
        store, _ = _make_store(tmp)
        store.register_project(r"D:\space\myproject")
        s1 = store.create_session(r"D:\space\myproject", title="First")
        s2 = store.create_session(r"D:\space\myproject", title="Second")
        sessions = store.list_sessions(r"D:\space\myproject")
        assert len(sessions) == 2
        # Most recent first
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_session_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agentcore.session_store'`

- [ ] **Step 3: 实现 SessionStore**

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_session_store.py -v`
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add agentcore/session_store.py tests/test_session_store.py
git commit -m "feat: add SessionStore — project/session CRUD with persistent storage"
```

---

### Task 3: config.py 支持 data_dir

**Files:**
- Modify: `agentcore/config.py`

- [ ] **Step 1: 改造 AgentConfig.from_yaml() 接受 data_dir**

在 `AgentConfig` 中新增 `data_dir` 字段，修改 `from_yaml()` 方法从 `{data_dir}/config.yaml` 读取。保留向后兼容——不传 `data_dir` 时行为不变。

```python
# agentcore/config.py — 只展示改动部分

# 在 AgentConfig dataclass 中新增字段:
data_dir: str | None = None  # .ai-code-agent/ 目录的绝对路径

# 修改 from_yaml() 方法:
@classmethod
def from_yaml(cls, path: str | None = None, data_dir: str | None = None) -> "AgentConfig":
    """Load configuration. If data_dir is set, read from {data_dir}/config.yaml."""
    import yaml

    cfg: dict = {}

    if path:
        config_path = Path(path)
    elif data_dir:
        # New path: .ai-code-agent/config.yaml
        config_path = Path(data_dir) / "config.yaml"
    else:
        # Legacy: PyInstaller exe dir or cwd
        if getattr(sys, 'frozen', False):
            exe_dir = Path(sys.executable).parent
            config_path = exe_dir / "config.yaml"
            if not config_path.exists():
                meipass = getattr(sys, '_MEIPASS', '')
                if meipass:
                    meipass_path = Path(meipass) / "config.yaml"
                    if meipass_path.exists():
                        config_path = meipass_path
        else:
            config_path = Path("config.yaml")

    if not config_path.exists():
        # Try example as fallback
        example = Path("config.example.yaml")
        if example.exists():
            config_path = example
        else:
            # Auto-generate defaults
            cfg = {
                "provider": "anthropic",
                "model": "claude-sonnet-4-6-20250514",
                "max_turns": 50,
                "max_messages": 200,
                "verbose": False,
                "api_keys": {},
                "base_urls": {},
                "models": {},
                "context_windows": {},
                "compact_thresholds": {},
                "reserved_outputs": {},
            }
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

    # ── 两级配置合并: 项目级 .myagent/config.yaml 覆盖全局 ──
    if data_dir:
        project_cwd = os.environ.get("AGENT_CWD") or cfg.get("cwd")
        if project_cwd:
            project_config = Path(project_cwd) / ".myagent" / "config.yaml"
            if project_config.exists():
                with open(project_config, "r", encoding="utf-8") as f:
                    project_cfg = yaml.safe_load(f) or {}
                # Project overrides global (shallow merge)
                for key in ("provider", "model", "api_key", "api_keys",
                            "base_url", "base_urls", "models",
                            "context_window", "context_windows",
                            "compact_threshold", "compact_thresholds",
                            "reserved_output", "reserved_outputs"):
                    if key in project_cfg:
                        cfg[key] = project_cfg[key]

    # ── 以下不变: env var overrides ──
    provider = (
        os.environ.get("AGENT_PROVIDER")
        or cfg.get("provider")
        or "anthropic"
    )
    api_key = os.environ.get("AGENT_API_KEY") or cfg.get("api_key")
    if not api_key:
        api_key = cfg.get("api_keys", {}).get(provider, "")
    if not api_key:
        provider_env_keys = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "glm": "GLM_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
        }
        api_key = os.environ.get(provider_env_keys.get(provider, "")) or ""

    base_url = os.environ.get("AGENT_BASE_URL") or cfg.get("base_url")
    if not base_url:
        base_url = cfg.get("base_urls", {}).get(provider, "")

    DEFAULT_CONTEXTS = {
        "anthropic": 200000, "openai": 128000,
        "glm": 128000, "deepseek": 64000,
    }

    context_window = int(
        os.environ.get("AGENT_CONTEXT_WINDOW")
        or cfg.get("context_window")
        or cfg.get("context_windows", {}).get(provider)
        or DEFAULT_CONTEXTS.get(provider, 128000)
    )
    compact_threshold = float(
        os.environ.get("AGENT_COMPACT_THRESHOLD")
        or cfg.get("compact_threshold")
        or cfg.get("compact_thresholds", {}).get(provider)
        or 0.85
    )
    reserved_output = int(
        os.environ.get("AGENT_RESERVED_OUTPUT")
        or cfg.get("reserved_output")
        or cfg.get("reserved_outputs", {}).get(provider)
        or 8000
    )

    agent_presets = cfg.get("agent_presets", {})
    normalized_presets = {}
    for pname, pdata in agent_presets.items():
        normalized_presets[pname] = {
            "provider": pdata.get("provider", ""),
            "allowed_tools": pdata.get("allowed_tools", []),
        }

    return cls(
        provider=provider,
        model=os.environ.get("AGENT_MODEL") or cfg.get("model"),
        api_key=api_key or None,
        base_url=base_url or None,
        cwd=os.environ.get("AGENT_CWD") or cfg.get("cwd"),
        max_turns=int(os.environ.get("AGENT_MAX_TURNS") or cfg.get("max_turns", 50)),
        max_messages=int(os.environ.get("AGENT_MAX_MESSAGES") or cfg.get("max_messages", 200)),
        verbose=bool(
            os.environ.get("AGENT_VERBOSE")
            or cfg.get("verbose", False)
        ),
        context_window=context_window,
        compact_threshold=compact_threshold,
        reserved_output=reserved_output,
        agent_presets=normalized_presets,
        data_dir=data_dir,
    )
```

同时修改 `get_agent_provider_config` 使用 `data_dir` 路径：

```python
def get_agent_provider_config(self, preset_name: str) -> dict | None:
    preset = self.agent_presets.get(preset_name.lower())
    if not preset or not preset.get("provider"):
        return None

    provider = preset["provider"]
    import yaml
    # Use data_dir-aware path
    if self.data_dir:
        config_path = Path(self.data_dir) / "config.yaml"
    else:
        config_path = Path("config.yaml")
    cfg = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

    return {
        "provider": provider,
        "api_key": cfg.get("api_keys", {}).get(provider, ""),
        "base_url": cfg.get("base_urls", {}).get(provider, ""),
        "model": cfg.get("models", {}).get(provider, ""),
    }
```

- [ ] **Step 2: 运行现有测试确认没有回归**

Run: `python -m pytest tests/ -v --timeout=10`
Expected: All existing tests pass (from_yaml 不传 data_dir 时行为不变)

- [ ] **Step 3: 提交**

```bash
git add agentcore/config.py
git commit -m "feat: config.py supports data_dir — reads from .ai-code-agent/config.yaml"
```

---

### Task 4: main.py 解析 --data-dir

**Files:**
- Modify: `agentcore/main.py`

- [ ] **Step 1: 添加 --data-dir 解析，传递给 AgentConfig 和 ws_server**

在 `main.py` 的 `main()` 函数中解析 `--data-dir` 参数：

```python
# agentcore/main.py — 改动部分

def _parse_data_dir() -> str | None:
    """Parse --data-dir from sys.argv."""
    if "--data-dir" in sys.argv:
        idx = sys.argv.index("--data-dir")
        if idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
    return None


def _resolve_data_dir() -> str:
    """Resolve data directory: --data-dir arg > default .ai-code-agent/."""
    explicit = _parse_data_dir()
    if explicit:
        return explicit
    # Default: project root / .ai-code-agent/
    return str(Path(__file__).parent.parent / ".ai-code-agent")


async def main():
    data_dir = _resolve_data_dir()
    config = AgentConfig.from_yaml(data_dir=data_dir)

    if "--ws" in sys.argv:
        from agentcore.ws_server import run_ws_server
        port_idx = sys.argv.index("--port") if "--port" in sys.argv else -1
        port = int(sys.argv[port_idx + 1]) if port_idx != -1 else 18765
        _reload = "--reload" in sys.argv
        await run_ws_server(config, port, reload=_reload, data_dir=data_dir)
        return

    if len(sys.argv) >= 3 and sys.argv[1] == "-c":
        await run_one_shot(config, " ".join(sys.argv[2:]))
    elif len(sys.argv) >= 2 and sys.argv[1] == "-s":
        await run_interactive(config)
    elif len(sys.argv) >= 2 and sys.argv[1] not in ("-s", "-c"):
        await run_one_shot(config, " ".join(sys.argv[1:]))
    else:
        pass
```

- [ ] **Step 2: 提交**

```bash
git add agentcore/main.py
git commit -m "feat: main.py parses --data-dir, passes to config and ws_server"
```

---

### Task 5: Tauri main.rs 传 --data-dir

**Files:**
- Modify: `ui/src-tauri/src/main.rs`

- [ ] **Step 1: 改造 get_backend_cmd 传递 --data-dir**

```rust
// ui/src-tauri/src/main.rs — 改动部分

fn get_backend_cmd(app: &tauri::AppHandle) -> Option<(String, Vec<String>)> {
    let resource_dir = app.path().resource_dir().ok()?;
    let bundled_exe = resource_dir.join("agentcore").join("agentcore.exe");

    if bundled_exe.exists() {
        // Packaged mode: data dir in AppData
        let app_data = app.path().app_data_dir().ok()?;
        let data_dir = app_data.join(".ai-code-agent");
        return Some((
            bundled_exe.to_string_lossy().to_string(),
            vec![
                "--ws".to_string(),
                "--port".to_string(), "18765".to_string(),
                "--data-dir".to_string(), data_dir.to_string_lossy().to_string(),
            ],
        ));
    }

    // Dev mode: data dir in project root
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let project_root = manifest_dir.join("..").join("..");
    let data_dir = project_root.join(".ai-code-agent");
    let main_py = project_root.join("agentcore").join("main.py");
    Some((
        "python".to_string(),
        vec![
            main_py.to_string_lossy().to_string(),
            "--ws".to_string(),
            "--port".to_string(), "18765".to_string(),
            "--data-dir".to_string(), data_dir.to_string_lossy().to_string(),
        ],
    ))
}
```

- [ ] **Step 2: 提交**

```bash
git add ui/src-tauri/src/main.rs
git commit -m "feat: main.rs passes --data-dir to Python backend (AppData or project root)"
```

---

### Task 6: ws_server.py 集成 SessionStore

**Files:**
- Modify: `agentcore/ws_server.py`

- [ ] **Step 1: run_ws_server 接受 data_dir，初始化 SessionStore**

在 `run_ws_server` 函数签名中加 `data_dir: str | None = None`：

```python
async def run_ws_server(config: AgentConfig, port: int = 18765,
                         reload: bool = False, data_dir: str | None = None):
    """Start WebSocket server. Called from main.py --ws mode."""
    from agentcore.data_dir import DataDir
    from agentcore.session_store import SessionStore

    # Initialize data directory
    effective_data_dir = data_dir or str(Path(__file__).parent.parent / ".ai-code-agent")
    dd = DataDir(Path(effective_data_dir))
    dd.init()
    store = SessionStore(dd)

    watch_root = Path(__file__).parent
    while True:
        user_agents = load_user_agents(config.cwd)
        manager = SubagentManager(config, user_agents)
        master_state = manager.agents["master"]
        await master_state.controller.connect_mcp()

        async def handler(websocket):
            await _handle_client(websocket, manager, store, dd)

        # ... rest unchanged
```

- [ ] **Step 2: _handle_client 接受 store 和 dd，新增 WebSocket 消息类型**

```python
async def _handle_client(websocket: ServerConnection, manager: SubagentManager,
                          store: SessionStore, dd: DataDir):
    # ... existing handler setup unchanged ...

    async for raw_message in websocket:
        try:
            msg = json.loads(raw_message)
        except json.JSONDecodeError:
            await websocket.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
            continue

        msg_type = msg.get("type", "")
        try:
            # ── Existing handlers unchanged (send_message, cancel, etc.) ──
            if msg_type == "send_message":
                # ... existing code ...
                pass
            elif msg_type == "cancel":
                pass
            # ... (all existing elif branches stay the same) ...

            # ── NEW: Project / Session messages ──
            elif msg_type == "list_projects":
                projects = store.list_projects()
                await websocket.send(json.dumps({
                    "type": "projects", "projects": projects,
                }, ensure_ascii=False))

            elif msg_type == "open_project":
                project_path = msg.get("path", "")
                store.register_project(project_path)
                store.touch_project(project_path)
                sessions = store.list_sessions(project_path)
                await websocket.send(json.dumps({
                    "type": "project_opened",
                    "path": project_path,
                    "sessions": sessions,
                }, ensure_ascii=False))

            elif msg_type == "create_session":
                project_path = msg.get("project_path", "")
                title = msg.get("title", "New Chat")
                session_id = store.create_session(project_path, title=title)
                await websocket.send(json.dumps({
                    "type": "session_created",
                    "session_id": session_id,
                    "title": title,
                }, ensure_ascii=False))

            elif msg_type == "load_session":
                project_path = msg.get("project_path", "")
                session_id = msg.get("session_id", "")
                messages = store.load_messages(project_path, session_id)
                meta = store.get_session_meta(project_path, session_id)
                await websocket.send(json.dumps({
                    "type": "session_loaded",
                    "session_id": session_id,
                    "messages": messages,
                    "meta": meta,
                }, ensure_ascii=False))

            elif msg_type == "list_all_sessions":
                """Browse sessions across all projects (for 'More' button)."""
                projects = store.list_projects()
                all_sessions = []
                for p in projects:
                    sessions = store.list_sessions(p["path"])
                    for s in sessions:
                        s["project_path"] = p["path"]
                        s["project_name"] = p.get("name", "")
                    all_sessions.extend(sessions)
                all_sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
                await websocket.send(json.dumps({
                    "type": "all_sessions", "sessions": all_sessions,
                }, ensure_ascii=False))

            elif msg_type == "shutdown":
                break
        except Exception as e:
            await websocket.send(json.dumps({
                "type": "error", "message": str(e),
            }, ensure_ascii=False))
```

- [ ] **Step 3: 提交**

```bash
git add agentcore/ws_server.py
git commit -m "feat: ws_server integrates SessionStore — project/session WebSocket API"
```

---

### Task 7: Agent 实时持久化消息

**Files:**
- Modify: `agentcore/agent.py`

- [ ] **Step 1: Agent 持有 session_id 和 store 引用，在 run_stream 中实时写消息**

在 `Agent.__init__` 中新增可选的 session 存储参数：

```python
# agentcore/agent.py — 改动部分

class Agent:
    def __init__(
        self,
        provider: BaseProvider,
        registry: ToolRegistry,
        cwd: str | None = None,
        max_turns: int = 50,
        max_messages: int = 200,
        # ... existing params ...
        # NEW: session persistence
        session_store=None,       # SessionStore instance
        session_project: str | None = None,
        session_id: str | None = None,
    ):
        # ... existing init ...
        self._session_store = session_store
        self._session_project = session_project
        self._session_id = session_id

    def _persist_message(self, message: Message):
        """Append a message to the session store if configured."""
        if not self._session_store or not self._session_id:
            return
        msg_dict = {
            "role": message.role,
            "content": message.content or "",
        }
        if message.tool_use_id:
            msg_dict["tool_use_id"] = message.tool_use_id
        if message.tool_use_blocks:
            msg_dict["tool_use_blocks"] = [
                {"tool_use_id": b.tool_use_id, "tool_name": b.tool_name, "input": b.input}
                for b in message.tool_use_blocks
            ]
        if message.id:
            msg_dict["id"] = message.id
        if message.usage:
            msg_dict["usage"] = message.usage
        self._session_store.append_message(
            self._session_project, self._session_id, msg_dict
        )

    def _persist_llm_log(self, raw_response: dict):
        """Log LLM request/response details."""
        if not self._session_store or not self._session_id:
            return
        self._session_store.append_llm_log(
            self._session_project, self._session_id, raw_response
        )
```

在 `run_stream` 方法中，每次 `self.messages.append()` 后调用 `_persist_message`：

```python
# In run_stream, after each self.messages.append(...):
# Add self._persist_message(msg) right after the append

# After appending user message:
self.messages.append(Message(role="user", content=user_message))
self._persist_message(self.messages[-1])

# After ResponseDoneEvent (streaming assistant):
self.messages.append(_streaming_asst)
_streaming_asst_added = True
self._persist_message(_streaming_asst)
self._persist_llm_log(event.raw)

# After tool result:
self.messages.append(Message(role="user", content=result_text, tool_use_id=block.tool_use_id))
self._persist_message(self.messages[-1])
```

- [ ] **Step 2: 提交**

```bash
git add agentcore/agent.py
git commit -m "feat: Agent persists messages to SessionStore in real-time"
```

---

### Task 8: .gitignore 和收尾

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: 加 .ai-code-agent/ 到 .gitignore**

在 `.gitignore` 的 `# Local config` 部分加入：

```
# Data directory
.ai-code-agent/
```

- [ ] **Step 2: 提交**

```bash
git add .gitignore
git commit -m "chore: add .ai-code-agent/ to .gitignore"
```

---

## Self-Review

**1. Spec coverage:**
- ✅ 路径解析（开发/打包模式）— Task 3, 4, 5
- ✅ `.ai-code-agent/` 目录结构 — Task 1
- ✅ project/session CRUD — Task 2
- ✅ config.yaml 从 data_dir 读取 — Task 3
- ✅ 项目级 `.myagent/config.yaml` 覆盖 — Task 3
- ✅ Tauri 传 `--data-dir` — Task 5
- ✅ WebSocket session API — Task 6
- ✅ 实时消息持久化 — Task 7
- ✅ .gitignore — Task 8
- ⚠️ LLM 日志和系统日志的按天滚动 — 未包含（可后续迭代，当前 append-only 足够）
- ⚠️ config.local.json（UI 偏好）读写 — 未包含（前端改动，可后续迭代）

**2. Placeholder scan:** 无 TBD/TODO。

**3. Type consistency:** `data_dir: str | None` 在 config.py、main.py、ws_server.py 中一致。`SessionStore` 方法签名在 Task 2 定义，Task 6/7 使用时匹配。

---

### Task 9: 前端 session Pinia store

**Files:**
- Create: `ui/src/stores/session.ts`

- [ ] **Step 1: 创建 session store，管理项目和 session 状态**

```typescript
// ui/src/stores/session.ts
import { ref } from 'vue';
import { defineStore } from 'pinia';
import { agentWs } from '../services/agentWs';

export interface ProjectInfo {
  hash: string;
  path: string;
  name: string;
  last_opened: string;
}

export interface SessionInfo {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  model: string;
  msg_count: number;
  project_path?: string;
  project_name?: string;
}

export const useSessionStore = defineStore('session', () => {
  const projects = ref<ProjectInfo[]>([]);
  const currentProjectPath = ref<string>('');
  const currentProjectName = ref<string>('');
  const sessions = ref<SessionInfo[]>([]);
  const currentSessionId = ref<string>('');

  function setProjects(list: ProjectInfo[]) {
    projects.value = list;
  }

  function setProjectOpened(path: string, sessionList: SessionInfo[]) {
    currentProjectPath.value = path;
    const p = projects.value.find(p => p.path === path);
    currentProjectName.value = p?.name || path.split(/[\\/]/).pop() || '';
    sessions.value = sessionList;
  }

  function setSessionCreated(sessionId: string, title: string) {
    currentSessionId.value = sessionId;
    sessions.value.unshift({
      session_id: sessionId,
      title,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      model: '',
      msg_count: 0,
    });
  }

  function setCurrentSession(sessionId: string) {
    currentSessionId.value = sessionId;
  }

  function openProject(path: string) {
    agentWs.send({ type: 'open_project', path });
  }

  function createSession(title: string = 'New Chat') {
    agentWs.send({ type: 'create_session', project_path: currentProjectPath.value, title });
  }

  function loadSession(sessionId: string) {
    agentWs.send({ type: 'load_session', project_path: currentProjectPath.value, session_id: sessionId });
  }

  function listProjects() {
    agentWs.send({ type: 'list_projects' });
  }

  function listAllSessions() {
    agentWs.send({ type: 'list_all_sessions' });
  }

  return {
    projects, currentProjectPath, currentProjectName,
    sessions, currentSessionId,
    setProjects, setProjectOpened, setSessionCreated, setCurrentSession,
    openProject, createSession, loadSession, listProjects, listAllSessions,
  };
});
```

- [ ] **Step 2: 提交**

```bash
git add ui/src/stores/session.ts
git commit -m "feat: add session Pinia store — project/session state management"
```

---

### Task 10: 前端 agentWs 事件监听

**Files:**
- Modify: `ui/src/services/agentWs.ts`

- [ ] **Step 1: 在 App.vue 中注册 session 相关事件（不需要改 agentWs.ts 本身）**

`agentWs.ts` 已经是通用事件系统（`on(event, callback)`），无需改动。前端只需在 `App.vue` 中新增事件监听。

修改 `ui/src/App.vue`，在 `onMounted` 中注册 session 事件：

```typescript
// App.vue — 在 onMounted 中追加:

// Session events
import { useSessionStore } from './stores/session';
const sessionStore = useSessionStore();

agentWs.on('projects', (d: any) => sessionStore.setProjects(d.projects));
agentWs.on('project_opened', (d: any) => sessionStore.setProjectOpened(d.path, d.sessions));
agentWs.on('session_created', (d: any) => sessionStore.setSessionCreated(d.session_id, d.title));
agentWs.on('session_loaded', (d: any) => {
  sessionStore.setCurrentSession(d.session_id);
  chatStore.loadMessages(
    (d.messages || []).map((m: any) => ({ role: m.role, content: m.content }))
  );
});
agentWs.on('all_sessions', (d: any) => {
  // Show in session browser (handled by SessionList component)
});

// On connect, load project list
agentWs.on('connected', () => {
  agentWs.send({ type: 'get_status' });
  sessionStore.listProjects();
});
```

- [ ] **Step 2: 提交**

```bash
git add ui/src/App.vue
git commit -m "feat: App.vue registers session WebSocket events"
```

---

### Task 11: ProjectPicker 组件

**Files:**
- Create: `ui/src/components/ProjectPicker.vue`

- [ ] **Step 1: 创建项目选择对话框**

```vue
<template>
  <div class="picker-overlay" @click.self="$emit('close')">
    <div class="picker-dialog">
      <h3>选择项目</h3>
      <div class="picker-search">
        <input v-model="search" placeholder="输入项目路径..." class="picker-input" />
        <button class="btn-open" @click="openPath" :disabled="!search.trim()">打开</button>
      </div>
      <div class="picker-list">
        <div v-for="p in filteredProjects" :key="p.path"
             class="picker-item" @click="selectProject(p.path)">
          <span class="picker-name">{{ p.name }}</span>
          <span class="picker-path">{{ p.path }}</span>
        </div>
        <div v-if="!filteredProjects.length" class="picker-empty">
          没有历史项目，请输入路径打开
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useSessionStore } from '../stores/session';

defineEmits(['close']);
const sessionStore = useSessionStore();
const search = ref('');

const filteredProjects = computed(() => {
  if (!search.value.trim()) return sessionStore.projects;
  const q = search.value.toLowerCase();
  return sessionStore.projects.filter(
    p => p.name.toLowerCase().includes(q) || p.path.toLowerCase().includes(q)
  );
});

function selectProject(path: string) {
  sessionStore.openProject(path);
}

function openPath() {
  if (search.value.trim()) {
    sessionStore.openProject(search.value.trim());
  }
}
</script>

<style scoped>
.picker-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.2); display: flex; align-items: center; justify-content: center; z-index: 200; }
.picker-dialog { background: white; border-radius: 10px; padding: 20px; min-width: 420px; max-height: 60vh; display: flex; flex-direction: column; box-shadow: 0 4px 20px rgba(0,0,0,0.15); }
.picker-dialog h3 { font-size: 16px; margin-bottom: 12px; }
.picker-search { display: flex; gap: 8px; margin-bottom: 12px; }
.picker-input { flex: 1; padding: 6px 10px; border: 1px solid #E2E6EC; border-radius: 6px; font-size: 14px; outline: none; }
.picker-input:focus { border-color: #6366F1; }
.btn-open { padding: 6px 16px; border: none; border-radius: 6px; background: #6366F1; color: white; cursor: pointer; font-size: 13px; }
.btn-open:disabled { background: #A5B4FC; cursor: not-allowed; }
.picker-list { overflow-y: auto; flex: 1; }
.picker-item { padding: 8px 10px; border-radius: 6px; cursor: pointer; display: flex; flex-direction: column; gap: 2px; }
.picker-item:hover { background: #F1F3F6; }
.picker-name { font-size: 14px; font-weight: 500; color: #1E1B3A; }
.picker-path { font-size: 12px; color: #94A3B8; }
.picker-empty { color: #94A3B8; font-size: 13px; padding: 16px 0; text-align: center; }
</style>
```

- [ ] **Step 2: 提交**

```bash
git add ui/src/components/ProjectPicker.vue
git commit -m "feat: add ProjectPicker — project selection dialog"
```

---

### Task 12: SessionList 组件

**Files:**
- Create: `ui/src/components/SessionList.vue`

- [ ] **Step 1: 创建 session 列表组件，显示在侧边栏中**

```vue
<template>
  <div class="session-list">
    <div class="session-header">
      <h3>{{ sessionStore.currentProjectName || 'Sessions' }}</h3>
      <div class="session-actions">
        <button class="btn-new" @click="newChat" title="新对话">+</button>
        <button class="btn-more" @click="$emit('showMore')" title="更多">···</button>
      </div>
    </div>
    <div class="session-items">
      <div v-for="s in sessionStore.sessions" :key="s.session_id"
           :class="['session-item', { active: s.session_id === sessionStore.currentSessionId }]"
           @click="switchSession(s.session_id)">
        <span class="session-title">{{ s.title }}</span>
        <span class="session-meta">{{ s.msg_count }}条 · {{ formatTime(s.updated_at) }}</span>
      </div>
      <div v-if="!sessionStore.sessions.length" class="session-empty">
        暂无对话，点击 + 开始
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useSessionStore } from '../stores/session';

defineEmits(['showMore']);
const sessionStore = useSessionStore();

function newChat() {
  sessionStore.createSession();
}

function switchSession(id: string) {
  sessionStore.loadSession(id);
}

function formatTime(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return '刚刚';
  if (diffMin < 60) return `${diffMin}分钟前`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}小时前`;
  return `${d.getMonth() + 1}/${d.getDate()}`;
}
</script>

<style scoped>
.session-list { display: flex; flex-direction: column; height: 100%; }
.session-header { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #F1F3F6; margin-bottom: 4px; }
.session-header h3 { font-size: 14px; color: #1E1B3A; }
.session-actions { display: flex; gap: 4px; }
.btn-new, .btn-more { background: none; border: 1px solid #E2E6EC; border-radius: 5px; width: 24px; height: 24px; cursor: pointer; font-size: 14px; color: #6366F1; display: flex; align-items: center; justify-content: center; }
.session-items { flex: 1; overflow-y: auto; }
.session-item { padding: 6px 8px; border-radius: 6px; cursor: pointer; display: flex; flex-direction: column; gap: 2px; }
.session-item:hover { background: #F1F3F6; }
.session-item.active { background: #EBF5FF; }
.session-title { font-size: 13px; font-weight: 500; color: #1E1B3A; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.session-meta { font-size: 11px; color: #94A3B8; }
.session-empty { color: #94A3B8; font-size: 13px; padding: 16px 0; text-align: center; }
</style>
```

- [ ] **Step 2: 集成到 App.vue**

修改 `ui/src/App.vue`，把 SessionList 嵌入侧边栏，header 加项目切换按钮：

```vue
<template>
  <div class="app-layout">
    <header class="app-header">
      <button class="sidebar-toggle" @click="showSidebar = !showSidebar">&#9776;</button>
      <button class="project-btn" @click="showProjectPicker = true">
        {{ sessionStore.currentProjectName || '选择项目' }}
      </button>
      <span class="app-title">{{ agentStore.provider }} / {{ agentStore.model }}</span>
      <!-- ... existing header buttons ... -->
    </header>
    <div class="app-body">
      <div v-if="showSidebar" class="left-sidebar">
        <SessionList @showMore="showAllSessions = true" />
        <AgentSidebar />
      </div>
      <ChatView class="chat-main" />
      <DebugDrawer v-if="debugStore.open" />
    </div>
    <InputBar />
    <!-- ... existing dialogs ... -->
    <ProjectPicker v-if="showProjectPicker" @close="showProjectPicker = false" />
    <AllSessionsDialog v-if="showAllSessions" @close="showAllSessions = false" />
  </div>
</template>
```

- [ ] **Step 3: 提交**

```bash
git add ui/src/components/SessionList.vue ui/src/App.vue
git commit -m "feat: add SessionList component, integrate project/session into App.vue"
```

---

### Task 13: AllSessionsDialog（"更多"对话框）

**Files:**
- Create: `ui/src/components/AllSessionsDialog.vue`

- [ ] **Step 1: 创建跨项目 session 浏览对话框**

```vue
<template>
  <div class="session-overlay" @click.self="$emit('close')">
    <div class="session-dialog">
      <h3>所有对话</h3>
      <div class="session-search">
        <input v-model="search" placeholder="搜索对话..." class="session-input" />
      </div>
      <div class="all-sessions">
        <div v-for="s in filtered" :key="s.session_id" class="all-session-item" @click="load(s)">
          <span class="all-session-title">{{ s.title }}</span>
          <div class="all-session-meta">
            <span v-if="s.project_name" class="all-session-project">{{ s.project_name }}</span>
            <span>{{ s.msg_count }}条 · {{ formatTime(s.updated_at) }}</span>
          </div>
        </div>
        <div v-if="!filtered.length" class="session-empty">没有找到对话</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useSessionStore, type SessionInfo } from '../stores/session';
import { agentWs } from '../services/agentWs';

defineEmits(['close']);
const sessionStore = useSessionStore();
const search = ref('');
const allSessions = ref<SessionInfo[]>([]);

onMounted(() => {
  agentWs.send({ type: 'list_all_sessions' });
  const handler = (d: any) => {
    allSessions.value = d.sessions || [];
  };
  agentWs.on('all_sessions', handler);
});

const filtered = computed(() => {
  if (!search.value.trim()) return allSessions.value;
  const q = search.value.toLowerCase();
  return allSessions.value.filter(s =>
    s.title.toLowerCase().includes(q) ||
    (s.project_name || '').toLowerCase().includes(q)
  );
});

function load(s: SessionInfo) {
  if (s.project_path) {
    sessionStore.openProject(s.project_path);
    // After project opens, load the specific session
    setTimeout(() => sessionStore.loadSession(s.session_id), 100);
  }
}

function formatTime(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
}
</script>

<style scoped>
.session-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.2); display: flex; align-items: center; justify-content: center; z-index: 200; }
.session-dialog { background: white; border-radius: 10px; padding: 20px; min-width: 480px; max-height: 60vh; display: flex; flex-direction: column; box-shadow: 0 4px 20px rgba(0,0,0,0.15); }
.session-dialog h3 { font-size: 16px; margin-bottom: 12px; }
.session-input { width: 100%; padding: 6px 10px; border: 1px solid #E2E6EC; border-radius: 6px; font-size: 14px; outline: none; margin-bottom: 8px; box-sizing: border-box; }
.session-input:focus { border-color: #6366F1; }
.all-sessions { overflow-y: auto; flex: 1; }
.all-session-item { padding: 8px 10px; border-radius: 6px; cursor: pointer; display: flex; flex-direction: column; gap: 4px; }
.all-session-item:hover { background: #F1F3F6; }
.all-session-title { font-size: 14px; font-weight: 500; color: #1E1B3A; }
.all-session-meta { display: flex; gap: 8px; font-size: 12px; color: #94A3B8; }
.all-session-project { color: #6366F1; }
.session-empty { color: #94A3B8; font-size: 13px; padding: 16px 0; text-align: center; }
</style>
```

- [ ] **Step 2: 提交**

```bash
git add ui/src/components/AllSessionsDialog.vue
git commit -m "feat: add AllSessionsDialog — browse sessions across projects"
```
