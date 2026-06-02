# MCP 集成实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Agent 添加 MCP (Model Context Protocol) 支持，连接外部 stdio 服务器并动态发现/调用其工具

**Architecture:** `.mcp.json` 配置加载 → `MCPConnectionManager` 连接服务器 → 工具发现并包装为 `MCPTool` → 注入 `ToolRegistry` → Agent 无感调用

**Tech Stack:** Python `mcp` SDK、asyncio stdio transport、JSON Schema 透明传递

---

### Task 1: 安装依赖

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: 安装 mcp SDK**

```bash
pip install mcp
```

- [ ] **Step 2: 更新 requirements.txt**

在 `requirements.txt` 末尾追加：

```
mcp>=1.0.0
```

- [ ] **Step 3: 验证导入**

```bash
python -c "from mcp import ClientSession, StdioServerParameters; from mcp.client.stdio import stdio_client; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "feat: add mcp SDK dependency"
```

---

### Task 2: 配置加载 `mcp/config.py`

**Files:**
- Create: `mcp/__init__.py`
- Create: `mcp/config.py`

- [ ] **Step 1: 创建 mcp 包**

```bash
mkdir -p mcp
```

`mcp/__init__.py`（空文件）：

```python
```

- [ ] **Step 2: 编写配置加载器**

`mcp/config.py`：

```python
""".mcp.json config loader — mirrors src/services/mcp/config.ts."""

import json
import os
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class MCPServerConfig:
    """Parsed configuration for a single MCP server."""
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


def _expand_env(value: str) -> str:
    """Expand ${VAR} placeholders in a string."""
    import re
    def replacer(m):
        return os.environ.get(m.group(1), "")
    return re.sub(r'\$\{(\w+)\}', replacer, value)


def _expand_env_in(obj):
    """Recursively expand env vars in strings."""
    if isinstance(obj, str):
        return _expand_env(obj)
    elif isinstance(obj, list):
        return [_expand_env_in(v) for v in obj]
    elif isinstance(obj, dict):
        return {k: _expand_env_in(v) for k, v in obj.items()}
    return obj


def load_mcp_configs(cwd: Path | str) -> list[MCPServerConfig]:
    """Load .mcp.json from cwd and parent directories, merge by server name.

    Closer to cwd takes priority. Returns list of validated configs.
    """
    cwd = Path(cwd).resolve()
    merged: dict[str, dict] = {}

    # Walk cwd up to root, collecting .mcp.json files
    dirs = [cwd] + list(cwd.parents)
    for d in dirs:
        config_path = d / ".mcp.json"
        if not config_path.exists():
            continue
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        servers = data.get("mcpServers", {})
        if not isinstance(servers, dict):
            continue

        # Closer directories override parent configs
        for name, raw in servers.items():
            if not isinstance(raw, dict):
                continue
            if name not in merged:
                merged[name] = raw

    # Parse and validate
    configs: list[MCPServerConfig] = []
    for name, raw in reversed(merged.items()):  # reverse: closer dirs last
        command = raw.get("command", "")
        if not command:
            continue

        args = raw.get("args", [])
        env = raw.get("env", {})
        if isinstance(args, str):
            args = [args]
        if not isinstance(env, dict):
            env = {}

        # Expand env vars
        command = _expand_env(command)
        args = _expand_env_in(args)
        env = _expand_env_in(env)

        # Merge server env with process env
        full_env = {**os.environ, **env}

        configs.append(MCPServerConfig(
            name=name,
            command=command,
            args=args if isinstance(args, list) else [],
            env=full_env,
        ))

    return configs
```

- [ ] **Step 3: 验证配置加载**

```bash
cd D:/space/labspace/ai_codeagent && echo '{"mcpServers":{"test":{"command":"echo","args":["hello"]}}}' > .mcp.json
python -c "
from mcp.config import load_mcp_configs
from pathlib import Path
configs = load_mcp_configs(Path.cwd())
for c in configs:
    print(f'{c.name}: {c.command} {c.args}')
"
rm .mcp.json
```

Expected output: `test: echo ['hello']`

- [ ] **Step 4: Commit**

```bash
git add mcp/__init__.py mcp/config.py
git commit -m "feat: MCP config loader — .mcp.json parsing with env expansion"
```

---

### Task 3: 连接管理 + 工具包装 `mcp/connection.py`

**Files:**
- Create: `mcp/connection.py`

- [ ] **Step 1: 编写连接管理器和 MCPTool**

`mcp/connection.py`：

```python
"""MCP connection manager — mirrors src/services/mcp/client.ts connectToServer."""

import asyncio
import logging
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from tools.base import Tool, ToolContext
from mcp.config import MCPServerConfig

logger = logging.getLogger(__name__)


class MCPToolWrapper(Tool):
    """Wraps an MCP server tool as a project Tool.

    Mirrors src/tools/MCPTool/MCPTool.ts.
    """

    def __init__(self, server_name: str, tool, session: ClientSession):
        self.name = f"mcp__{server_name}__{tool.name}"
        self.description = tool.description or f"MCP tool: {tool.name}"
        self.parameters = tool.inputSchema if hasattr(tool, 'inputSchema') else {}
        self._server_name = server_name
        self._tool_name = tool.name
        self._session = session

    async def call(self, input: dict, context: ToolContext) -> str:
        try:
            result = await self._session.call_tool(self._tool_name, arguments=input)
            parts = []
            for item in result.content:
                if hasattr(item, 'text'):
                    parts.append(item.text)
                else:
                    parts.append(f"[{item.type}]")
            return "\n".join(parts) if parts else "(empty result)"
        except Exception as e:
            return f"MCP tool error [{self._server_name}/{self._tool_name}]: {e}"


class MCPConnectionManager:
    """Connects to MCP servers, discovers tools, and wraps them.

    connect_all() should be called once at agent init time.
    get_tools() returns all discovered tools for registry injection.
    """

    def __init__(self, servers: list[MCPServerConfig]):
        self._servers = servers
        self._tools: list[MCPToolWrapper] = []
        self._sessions: list[ClientSession] = []

    async def connect_all(self) -> None:
        """Connect to all configured servers concurrently.

        Failures are logged but do not block other servers or agent startup.
        """
        results = await asyncio.gather(
            *(self._connect_server(s) for s in self._servers),
            return_exceptions=True,
        )
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.warning(f"MCP server '{self._servers[i].name}': connection failed — {r}")

    async def _connect_server(self, config: MCPServerConfig) -> None:
        server_name = config.name
        params = StdioServerParameters(
            command=config.command,
            args=config.args,
            env=config.env if config.env else None,
        )

        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()

                for tool in tools_result.tools:
                    wrapper = MCPToolWrapper(server_name, tool, session)
                    self._tools.append(wrapper)

                logger.info(
                    f"MCP server '{server_name}': connected, {len(tools_result.tools)} tools")

                # Keep session alive — hold the async context
                self._sessions.append(session)

                # Wait forever — the session must stay open for future tool calls
                await asyncio.Event().wait()

    def get_tools(self) -> list[MCPToolWrapper]:
        """Return all discovered MCP tools."""
        return list(self._tools)

    async def close_all(self) -> None:
        """Close all server connections."""
        # Sessions are managed by async context managers;
        # cancelling connect tasks will clean them up
        pass
```

Wait — the `async with` blocks in `_connect_server` will close the session when the context exits. I need a different approach to keep sessions alive. Let me redesign.

- [ ] **Step 1 (revised): 用后台任务保持连接**

`mcp/connection.py`：

```python
"""MCP connection manager — mirrors src/services/mcp/client.ts connectToServer."""

import asyncio
import logging
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from tools.base import Tool, ToolContext
from mcp.config import MCPServerConfig

logger = logging.getLogger(__name__)


class MCPToolWrapper(Tool):
    """Wraps an MCP server tool as a project Tool."""

    def __init__(self, server_name: str, tool, session: ClientSession):
        self.name = f"mcp__{server_name}__{tool.name}"
        self.description = tool.description or f"MCP tool: {tool.name}"
        self.parameters = tool.inputSchema if hasattr(tool, 'inputSchema') else {}
        self._server_name = server_name
        self._tool_name = tool.name
        self._session = session

    async def call(self, input: dict, context: ToolContext) -> str:
        try:
            result = await self._session.call_tool(self._tool_name, arguments=input)
            parts = []
            for item in result.content:
                if hasattr(item, 'text'):
                    parts.append(item.text)
                else:
                    parts.append(f"[{item.type}]")
            return "\n".join(parts) if parts else "(empty result)"
        except Exception as e:
            return f"MCP tool error [{self._server_name}/{self._tool_name}]: {e}"


class MCPConnectionManager:
    """Connects to MCP servers, discovers tools.

    connect_all() starts background tasks for each server.
    get_tools() returns discovered tools for registry injection.
    """

    def __init__(self, servers: list[MCPServerConfig]):
        self._servers = servers
        self._tools: list[MCPToolWrapper] = []
        self._tasks: list[asyncio.Task] = []

    async def connect_all(self) -> None:
        """Start background connection tasks for all servers."""
        for server in self._servers:
            task = asyncio.create_task(self._run_server(server))
            self._tasks.append(task)

    async def _run_server(self, config: MCPServerConfig) -> None:
        """Connect to one server and hold the session open."""
        server_name = config.name
        try:
            params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env=config.env if config.env else None,
            )

            read, write = await stdio_client(params).__aenter__()
            session = ClientSession(read, write)
            await session.__aenter__()
            await session.initialize()

            tools_result = await session.list_tools()
            for tool in tools_result.tools:
                self._tools.append(MCPToolWrapper(server_name, tool, session))

            logger.info(f"MCP '{server_name}': {len(tools_result.tools)} tools")

            # Hold session open indefinitely
            while True:
                await asyncio.sleep(3600)

        except Exception as e:
            logger.warning(f"MCP '{server_name}': failed — {e}")

    def get_tools(self) -> list[MCPToolWrapper]:
        return list(self._tools)

    async def close_all(self) -> None:
        for task in self._tasks:
            task.cancel()
```

Hmm, manually calling `__aenter__` is fragile. Let me use the context manager properly in a background task.

Actually, the `async with` exits the context when the block ends. To keep it alive, I need the background task to stay inside the `async with`. Let me use `asyncio.Event()`.

- [ ] **Step 1 (final): 用 asyncio.Event 保持连接**

```python
"""MCP connection manager — mirrors src/services/mcp/client.ts connectToServer."""

import asyncio
import logging
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from tools.base import Tool, ToolContext
from mcp.config import MCPServerConfig

logger = logging.getLogger(__name__)


class MCPToolWrapper(Tool):
    """Wraps an MCP server tool as a project Tool."""

    def __init__(self, server_name: str, tool, session: ClientSession):
        self.name = f"mcp__{server_name}__{tool.name}"
        self.description = tool.description or f"MCP tool: {tool.name}"
        self.parameters = tool.inputSchema if hasattr(tool, 'inputSchema') else {}
        self._server_name = server_name
        self._tool_name = tool.name
        self._session = session

    async def call(self, input: dict, context: ToolContext) -> str:
        try:
            result = await self._session.call_tool(self._tool_name, arguments=input)
            parts = []
            for item in result.content:
                if hasattr(item, 'text'):
                    parts.append(item.text)
                else:
                    parts.append(f"[{item.type}]")
            return "\n".join(parts) if parts else "(empty result)"
        except Exception as e:
            return f"MCP tool error [{self._server_name}/{self._tool_name}]: {e}"


class MCPConnectionManager:
    """Connects to MCP servers, discovers tools.

    connect_all() starts background tasks for each server.
    get_tools() returns discovered tools for registry injection.
    """

    def __init__(self, servers: list[MCPServerConfig]):
        self._servers = servers
        self._tools: list[MCPToolWrapper] = []
        self._tasks: list[asyncio.Task] = []

    async def connect_all(self) -> None:
        """Start background connection tasks for all servers."""
        for server in self._servers:
            task = asyncio.create_task(self._run_server(server))
            self._tasks.append(task)

    async def _run_server(self, config: MCPServerConfig) -> None:
        """Connect to one server and hold the session open."""
        server_name = config.name
        try:
            params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env=config.env if config.env else None,
            )

            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    tools_result = await session.list_tools()
                    for tool in tools_result.tools:
                        self._tools.append(MCPToolWrapper(server_name, tool, session))

                    logger.info(f"MCP '{server_name}': {len(tools_result.tools)} tools")

                    # Hold session open until cancelled
                    await asyncio.Event().wait()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"MCP '{server_name}': failed — {e}")

    def get_tools(self) -> list[MCPToolWrapper]:
        return list(self._tools)

    async def close_all(self) -> None:
        for task in self._tasks:
            task.cancel()
```

- [ ] **Step 2: 验证导入和基本结构**

```bash
cd D:/space/labspace/ai_codeagent
python -c "
from mcp.connection import MCPConnectionManager, MCPToolWrapper
from mcp.config import MCPServerConfig
print('Import OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add mcp/connection.py
git commit -m "feat: MCP connection manager + tool wrapper"
```

---

### Task 4: 集成到 Agent

**Files:**
- Modify: `controller.py`

- [ ] **Step 1: 在 controller.py 中集成 MCP**

修改 `controller.py` 的 `AgentController.__init__`，在 `_build_registry` 后连接 MCP：

```python
# 在 __init__ 中，_build_registry() 返回后：
self.registry = _build_registry()
self.provider = _build_provider(config)

# MCP integration
self._mcp_manager: MCPConnectionManager | None = None
self._mcp_task: asyncio.Task | None = None

# 在 __init__ 末尾启动 MCP 后台连接
self._start_mcp(config.cwd)
```

添加方法：

```python
def _start_mcp(self, cwd: str | None):
    """Start MCP server connections in background."""
    from mcp.config import load_mcp_configs, MCPServerConfig
    from mcp.connection import MCPConnectionManager

    cwd_path = Path(cwd) if cwd else Path.cwd()
    configs = load_mcp_configs(cwd_path)
    if not configs:
        return

    self._mcp_manager = MCPConnectionManager(configs)

    async def _connect_and_register():
        await self._mcp_manager.connect_all()
        for tool in self._mcp_manager.get_tools():
            self.registry.register(tool)

    self._mcp_task = asyncio.ensure_future(_connect_and_register())
```

Wait, the `__init__` is synchronous but MCP connection is async. We can't use `asyncio.ensure_future` easily in `__init__` without a running event loop.

Let me rethink. The existing `AgentController.__init__` is synchronous. The `send_message` method runs in an event loop. Let me defer MCP connection to first use.

Actually, in the Flet app, `__init__` runs in the event loop (Flet is async). Let me check if `asyncio.get_event_loop()` is available at init time.

Let me check how `AgentController` is created in `app.py`:

```python
self.controller = AgentController(config, self.handler)
```

This is inside `FletApp.__init__`, which runs in the Flet event loop. So `asyncio.get_running_loop()` should work.

Let me update the plan to start MCP connection in a background task during init.

Actually, looking more carefully, `send_message` is called via `page.run_task` or `asyncio.create_task`, so the event loop is available at init time.

- [ ] **Step 1 (revised): 修改 controller.py**

Add to `AgentController.__init__`, after `_build_registry()` and `_build_provider()`:

```python
self._mcp_manager = None
self._mcp_task = None
self._start_mcp(config.cwd)
```

Add helper method at class level:

```python
def _start_mcp(self, cwd: str | None):
    """Start MCP server connections in background."""
    from mcp.config import load_mcp_configs
    from mcp.connection import MCPConnectionManager

    cwd_path = Path(cwd) if cwd else Path.cwd()
    configs = load_mcp_configs(cwd_path)
    if not configs:
        return

    self._mcp_manager = MCPConnectionManager(configs)

    async def _connect_and_register():
        await self._mcp_manager.connect_all()
        for tool in self._mcp_manager.get_tools():
            self.registry.register(tool)

    try:
        loop = asyncio.get_running_loop()
        self._mcp_task = loop.create_task(_connect_and_register())
    except RuntimeError:
        pass  # no event loop yet, connect on first send_message
```

Also add MCP import at top of `controller.py`:

```python
import asyncio
```

(`asyncio` may already be imported — verify.)

- [ ] **Step 2: 验证集成不报错**

```bash
cd D:/space/labspace/ai_codeagent
python -c "
from controller import AgentController
from config import AgentConfig
# 不带 .mcp.json 时不应报错
print('OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add controller.py
git commit -m "feat: integrate MCP connection manager into AgentController"
```

---

### Task 5: 端到端验证

- [ ] **Step 1: 创建测试用 .mcp.json**

```bash
cd D:/space/labspace/ai_codeagent
echo '{"mcpServers":{"echo":{"command":"python","args":["-c","import json,sys; json.dump({\"tools\":[{\"name\":\"hello\",\"description\":\"Say hello\",\"inputSchema\":{\"type\":\"object\",\"properties\":{\"name\":{\"type\":\"string\"}}}}]},sys.stdout)"]}}}' > .mcp.json
```

Wait, that's not a real MCP server. A real MCP server needs to implement the MCP protocol. Let me use a simple test instead.

Actually, the simplest end-to-end test is to verify that:
1. Config loading works
2. Connection failure is gracefully handled
3. The agent still works without MCP servers

- [ ] **Step 1: 清理测试文件，启动项目**

```bash
cd D:/space/labspace/ai_codeagent
# 确保没有 .mcp.json
rm -f .mcp.json
# 正常启动
python main.py
```

Expected: 正常启动，无 MCP 相关报错

- [ ] **Step 2: Commit final state**

```bash
git status
```

---

### Self-Review

**Spec coverage:**
- Config loading → Task 2 ✓
- Connection management → Task 3 ✓
- Tool wrapping → Task 3 ✓
- Agent integration → Task 4 ✓
- Error handling (fail gracefully) → Tasks 3, 5 ✓

**Placeholder scan:** None.

**Type consistency:** `MCPServerConfig` defined in Task 2, used in Task 3 and Task 4 — consistent. `MCPToolWrapper` inherits from `Tool` (tools/base.py) — consistent with existing tool interface.
