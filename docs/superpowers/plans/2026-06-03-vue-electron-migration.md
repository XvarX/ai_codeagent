# Vue 3 + Electron 前端迁移实施计划

> **For agentic workers:** 使用 superpowers:executing-plans 或 superpowers:subagent-driven-development 来逐步实施。每步使用 checkbox (`- [ ]`) 跟踪。

**目标:** 将 Flet 前端迁移到 Vue 3 + Electron，保留 Python Agent 后端，功能全部对等。

**架构:** Python Agent 后端通过 WebSocket server 与 Vue 3 前端通信，Electron 主进程管理 Python 子进程生命周期。前端使用 Pinia 做状态管理，Vite 做构建。

**技术栈:** Vue 3 (Composition API), Pinia, Vite, TypeScript, Electron, Python websockets, PyInstaller

**说明:** 此计划分 6 个 Phase。Phase 1-2 是后端改造（可独立测试），Phase 3-5 是前端构建，Phase 6 是打包。

---

## Phase 1: 后端目录重构

### Task 1.1: 创建 agentcore 包目录

**文件:**
- Create: `agentcore/__init__.py`
- Create: `agentcore/config.py`
- Create: `agentcore/events.py`
- Create: `agentcore/core_types.py`
- Create: `agentcore/prompts.py`
- Create: `agentcore/agent_definitions.py`
- Create: `agentcore/agent.py`
- Create: `agentcore/controller.py`
- Create: `agentcore/agent_message_queue.py`
- Create: `agentcore/subagent_manager.py`

- [ ] **Step 1: 创建 agentcore 目录并初始化包**

```bash
mkdir -p agentcore/providers agentcore/tools agentcore/skills agentcore/compact agentcore/mcp_integration agentcore/flet_ui
touch agentcore/__init__.py
touch agentcore/providers/__init__.py
touch agentcore/tools/__init__.py
touch agentcore/skills/__init__.py
touch agentcore/compact/__init__.py
touch agentcore/mcp_integration/__init__.py
touch agentcore/flet_ui/__init__.py
```

- [ ] **Step 2: 移动所有 Python 文件到 agentcore/ 下，先不改 import**

```bash
# 根目录 Python 文件
mv config.py agentcore/
mv events.py agentcore/
mv core_types.py agentcore/
mv prompts.py agentcore/
mv agent_definitions.py agentcore/
mv agent.py agentcore/
mv controller.py agentcore/
mv agent_message_queue.py agentcore/
mv subagent_manager.py agentcore/

# 子目录
mv providers/*.py agentcore/providers/
mv tools/*.py agentcore/tools/
mv skills/*.py agentcore/skills/
mv compact/*.py agentcore/compact/
mv mcp_integration/*.py agentcore/mcp_integration/
mv flet_ui/*.py agentcore/flet_ui/

# 测试
mkdir -p agentcore/tests
mv tests/*.py agentcore/tests/
```

- [ ] **Step 3: 确认所有文件已移动**

```bash
ls agentcore/
# 应看到: __init__.py config.py events.py core_types.py prompts.py
# agent_definitions.py agent.py controller.py agent_message_queue.py
# subagent_manager.py providers/ tools/ skills/ compact/ mcp_integration/ flet_ui/ tests/
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: move all Python code into agentcore/ package"
```

---

### Task 1.2: 修复 agentcore 内部 import

**文件修改:** agentcore/ 下所有 .py 文件

所有内部 import 需要加上 `agentcore.` 前缀。以下是完整的 import 变更清单：

- [ ] **Step 1: 修复 `agentcore/core_types.py`** — 无本地 import，不需要改

- [ ] **Step 2: 修复 `agentcore/events.py`** — 无本地 import，不需要改

- [ ] **Step 3: 修复 `agentcore/config.py`** — 无本地 import，不需要改

- [ ] **Step 4: 修复 `agentcore/prompts.py`** — 无本地 import，不需要改

- [ ] **Step 5: 修复 `agentcore/agent_definitions.py`** — 无本地 import，不需要改

- [ ] **Step 6: 修复 `agentcore/providers/base.py`**

```python
# 改: from core_types import Message, ToolUseBlock
# 为:
from agentcore.core_types import Message, ToolUseBlock
```

- [ ] **Step 7: 修复 `agentcore/providers/anthropic.py`**

```python
# 改:
# from core_types import Message, ToolUseBlock
# from events import TextDeltaEvent, ToolUseEvent, ResponseDoneEvent, ErrorEvent
# 为:
from agentcore.core_types import Message, ToolUseBlock
from agentcore.events import TextDeltaEvent, ToolUseEvent, ResponseDoneEvent, ErrorEvent
```

- [ ] **Step 8: 修复 `agentcore/providers/openai_compat.py`**

```python
from agentcore.core_types import Message, ToolUseBlock
from agentcore.events import TextDeltaEvent, ToolUseEvent, ResponseDoneEvent, ErrorEvent
```

- [ ] **Step 9: 修复 `agentcore/compact/grouping.py`**

```python
# from core_types import Message
# 为:
from agentcore.core_types import Message
```

- [ ] **Step 10: 修复 `agentcore/compact/compact.py`**

```python
from agentcore.core_types import Message, ToolUseBlock
from agentcore.compact.grouping import group_by_api_round, estimate_tokens
from agentcore.compact.prompt import COMPACT_SYSTEM_PROMPT, build_compact_user_message, format_summary
```

- [ ] **Step 11: 修复 `agentcore/compact/autoCompact.py`**

```python
# from core_types import Message
# 为:
from agentcore.core_types import Message
```

- [ ] **Step 12: 修复 `agentcore/compact/postCompactCleanup.py`** — 无本地 import，不需要改

- [ ] **Step 13: 修复 `agentcore/compact/prompt.py`** — 无本地 import，不需要改

- [ ] **Step 14: 修复 `agentcore/tools/base.py`** — 无本地 import，不需要改

- [ ] **Step 15: 修复 `agentcore/tools/registry.py`**

```python
# from .base import Tool
# 为（保持相对 import，同一包内不受影响）:
from .base import Tool
```

- [ ] **Step 16: 修复 `agentcore/tools/agent_tool.py`**

```python
from agentcore.tools.base import Tool, ToolContext
from agentcore.agent_definitions import resolve_agent, list_all_agents
```

- [ ] **Step 17: 修复 `agentcore/tools/skill_tool.py`**

```python
from agentcore.tools.base import Tool, ToolContext
from agentcore.skills.loader import SkillDef
```

- [ ] **Step 18: 修复 `agentcore/tools/bash.py`** — 无本地 import，不需要改
- [ ] **Step 19: 修复 `agentcore/tools/file_read.py`** — 无本地 import，不需要改
- [ ] **Step 20: 修复 `agentcore/tools/file_edit.py`** — 无本地 import，不需要改
- [ ] **Step 21: 修复 `agentcore/tools/file_write.py`** — 无本地 import，不需要改
- [ ] **Step 22: 修复 `agentcore/tools/glob.py`** — 无本地 import，不需要改
- [ ] **Step 23: 修复 `agentcore/tools/grep.py`** — 无本地 import，不需要改

- [ ] **Step 24: 修复 `agentcore/skills/loader.py`** — 无本地 import，不需要改
- [ ] **Step 25: 修复 `agentcore/skills/skill_tool.py`**

```python
from agentcore.tools.base import Tool, ToolContext
from agentcore.skills.loader import SkillDef
```

- [ ] **Step 26: 修复 `agentcore/mcp_integration/connection.py`** — 无本地 import，不需要改
- [ ] **Step 27: 修复 `agentcore/mcp_integration/config.py`** — 无本地 import，不需要改

- [ ] **Step 28: 修复 `agentcore/agent.py`**

```python
from agentcore.core_types import Message, ToolUseBlock
from agentcore.tools.base import ToolContext
from agentcore.tools.registry import ToolRegistry
from agentcore.tools.tool_result_storage import (
    process_tool_result_block,
    apply_tool_result_budget,
    ContentReplacementState,
)
from agentcore.providers.base import BaseProvider
from agentcore.prompts import build_system_prompt
```

- [ ] **Step 29: 修复 `agentcore/controller.py`**

```python
from agentcore.config import AgentConfig
from agentcore.tools.registry import ToolRegistry
from agentcore.tools.bash import BashTool
from agentcore.tools.file_read import FileReadTool
from agentcore.tools.file_edit import FileEditTool
from agentcore.tools.file_write import FileWriteTool
from agentcore.tools.glob import GlobTool
from agentcore.tools.grep import GrepTool
from agentcore.providers.anthropic import AnthropicProvider
from agentcore.providers.openai_compat import OpenAICompatProvider
from agentcore.agent import Agent
from agentcore.events import (
    ThinkingEvent, TextDeltaEvent, ToolUseEvent, ToolDoneEvent,
    ResponseDoneEvent, DoneEvent, ErrorEvent, CompactCallEvent, CompactEvent, SnipEvent,
    SubagentDoneEvent,
)
```

- [ ] **Step 30: 修复 `agentcore/subagent_manager.py`**

```python
from agentcore.config import AgentConfig
from agentcore.controller import AgentController, EventHandler, _build_registry, _build_provider
from agentcore.agent_definitions import AgentDefinition
```

- [ ] **Step 31: 修复 `agentcore/agent_message_queue.py`**

```python
from agentcore.controller import AgentController
```

- [ ] **Step 32: 修复 `agentcore/main.py`**（如果存在这个文件。当前 main.py 在根目录，稍后处理）

类似修复路径即可：
```python
from agentcore.config import AgentConfig
from agentcore.agent import Agent
```

- [ ] **Step 33: 修复 `agentcore/tests/` 下的测试文件**

```python
# agentcore/tests/test_agent_definitions.py
from agentcore.agent_definitions import BUILTIN_AGENTS, resolve_agent, list_all_agents

# agentcore/tests/test_message_queue.py
from agentcore.agent_message_queue import AgentMessageQueue

# agentcore/tests/test_subagent_system.py
from agentcore.config import AgentConfig
from agentcore.agent_definitions import AgentDefinition
from agentcore.controller import EventHandler
```

- [ ] **Step 34: 修复 `agentcore/flet_ui/app.py`**

```python
from agentcore.config import AgentConfig
from agentcore.controller import AgentController
from agentcore.flet_ui.chat_view import ChatView, flatten_headings
from agentcore.flet_ui.input_bar import InputBar
from agentcore.flet_ui.debug_drawer import DebugDrawer
from agentcore.flet_ui.config_dialog import show_config_dialog
from agentcore.flet_ui.mcp_dialog import show_mcp_dialog
from agentcore.flet_ui.skill_dialog import show_skill_dialog
from agentcore.flet_ui.agent_sidebar import AgentSidebar
from agentcore.subagent_manager import SubagentManager
from agentcore.agent_definitions import load_user_agents
```

- [ ] **Step 35: 修复其他 flet_ui/ 文件**

```python
# agentcore/flet_ui/agent_config.py
from agentcore.agent_definitions import BUILTIN_AGENTS
```

其他 flet_ui 文件（chat_view.py, input_bar.py, debug_drawer.py, config_dialog.py, mcp_dialog.py, skill_dialog.py, agent_sidebar.py, diff_viewer.py）只 import `flet` 和标准库，不需要改。

- [ ] **Step 36: 修复 `agentcore/controller.py` 中 `_build_registry` 和 `_load_provider_type` 的内部 import**

```python
# _build_registry 里
from agentcore.skills.loader import load_skills
from agentcore.skills.skill_tool import SkillTool

# _load_provider_type 里不需要改 import，但 config_path 需要改为找 ../config.yaml
# config_path = Path("config.yaml")
# 改为:
# config_path = Path(__file__).parent.parent / "config.yaml"
```

- [ ] **Step 37: Commit**

```bash
git add -A
git commit -m "refactor: fix all imports to use agentcore. prefix"
```

---

### Task 1.3: 创建根目录 main.py（入口兼容）

**文件:**
- Create: `main.py` (根目录，重新创建)
- Modify: `agentcore/main.py` (如果之前移入了旧版)

- [ ] **Step 1: 根目录 `main.py` 作为入口**

```python
"""Entry point for My Agent.

python main.py                  Qt 桌面界面 (默认)
python main.py -s               终端交互模式
python main.py -c "message"     单次命令行模式
python main.py --ws --port 18765  WebSocket server 模式
"""

import asyncio
import sys

from agentcore.config import AgentConfig
from agentcore.tools.registry import ToolRegistry
from agentcore.tools.bash import BashTool
from agentcore.tools.file_read import FileReadTool
from agentcore.tools.file_edit import FileEditTool
from agentcore.tools.file_write import FileWriteTool
from agentcore.tools.glob import GlobTool
from agentcore.tools.grep import GrepTool
from agentcore.providers.anthropic import AnthropicProvider
from agentcore.providers.openai_compat import OpenAICompatProvider
from agentcore.agent import Agent


def build_registry() -> tuple[ToolRegistry, str]:
    from agentcore.skills.loader import load_skills
    from agentcore.skills.skill_tool import SkillTool

    skills = load_skills()
    skill_tool = SkillTool(skills)
    skills_text = skill_tool.get_skill_list()

    registry = ToolRegistry()
    tools = [BashTool(), FileReadTool(), FileEditTool(),
             FileWriteTool(), GlobTool(), GrepTool()]
    if skills:
        tools.append(skill_tool)
    registry.register_all(tools)
    return registry, skills_text


def build_provider(config: AgentConfig):
    provider_name = config.provider.lower()
    if provider_name == "anthropic":
        return AnthropicProvider(
            model=config.model or "claude-sonnet-4-6-20250514",
            api_key=config.api_key,
            base_url=config.base_url,
        )
    else:
        return OpenAICompatProvider(
            provider=provider_name, model=config.model,
            api_key=config.api_key, base_url=config.base_url,
        )


# ... 保留原有的 _on_thinking, _on_tool_call, _on_tool_result,
#     run_one_shot, run_interactive, main 函数不变，
#     import 路径改为 agentcore.xxx


async def main():
    config = AgentConfig.from_yaml()

    if "--ws" in sys.argv:
        # WebSocket mode — handled by Phase 2
        # 仍然返回，Phase 2 会实现
        from agentcore.ws_server import run_ws_server
        port_idx = sys.argv.index("--port") if "--port" in sys.argv else -1
        port = int(sys.argv[port_idx + 1]) if port_idx != -1 else 18765
        await run_ws_server(config, port)
        return

    if len(sys.argv) >= 3 and sys.argv[1] == "-c":
        await run_one_shot(config, " ".join(sys.argv[2:]))
    elif len(sys.argv) >= 2 and sys.argv[1] == "-s":
        await run_interactive(config)
    elif len(sys.argv) >= 2 and sys.argv[1] not in ("-s", "-c"):
        await run_one_shot(config, " ".join(sys.argv[1:]))


if __name__ == "__main__":
    if len(sys.argv) == 1:
        from agentcore.flet_ui.app import launch_flet
        launch_flet(AgentConfig.from_yaml())
    else:
        asyncio.run(main())
```

- [ ] **Step 2: 删除 agentcore/ 下可能残留的旧 main.py**（如果被错误地移动了）

```bash
# 检查 agentcore/ 下是否有旧 main.py
ls agentcore/main.py 2>/dev/null
# 如果有旧版本（重复的 TUI 逻辑），删除它
rm -f agentcore/main.py 2>/dev/null
```

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "fix: restore root main.py with agentcore imports"
```

---

### Task 1.4: 验证 TUI 模式仍可用

- [ ] **Step 1: 运行 TUI 模式验证**

```bash
python main.py -c "echo hello"
```

Expected: 正常工作，agent 响应。

- [ ] **Step 2: 运行 Flet 桌面模式验证**

```bash
python main.py
```

Expected: Flet 窗口正常打开。

- [ ] **Step 3: 运行测试**

```bash
python -m pytest agentcore/tests/ -v
```

Expected: 所有测试通过。

- [ ] **Step 4: Commit**（任何修复后的提交）

---

## Phase 2: WebSocket Server

### Task 2.1: 创建 ws_server.py

**文件:**
- Create: `agentcore/ws_server.py`

- [ ] **Step 1: 安装 websockets 依赖**

```bash
pip install websockets
```

并在 `requirements.txt` 中添加：`websockets>=12.0`

- [ ] **Step 2: 创建 `agentcore/ws_server.py`**

```python
"""WebSocket server — bridges frontend ↔ AgentController.

Start: python main.py --ws --port 18765
"""

import asyncio
import json
import logging
from pathlib import Path

import websockets
from websockets.asyncio.server import serve, ServerConnection

from agentcore.config import AgentConfig
from agentcore.controller import AgentController, EventHandler

logger = logging.getLogger(__name__)


class WsEventHandler(EventHandler):
    """EventHandler that forwards all events as JSON over WebSocket."""

    def __init__(self, ws: ServerConnection):
        self._ws = ws

    async def _send(self, data: dict):
        try:
            await self._ws.send(json.dumps(data, ensure_ascii=False))
        except websockets.exceptions.ConnectionClosed:
            pass

    async def on_thinking(self):
        await self._send({"type": "thinking"})

    async def on_text_delta(self, token: str, reasoning: bool = False):
        await self._send({"type": "text_delta", "token": token, "reasoning": reasoning})

    async def on_tool_use(self, name: str, input_dict: dict, tool_use_id: str = ""):
        await self._send({
            "type": "tool_use", "name": name, "input": input_dict, "id": tool_use_id,
        })

    async def on_tool_result(self, name: str, result: str, is_error: bool,
                             duration_ms: float = 0, tool_use_id: str = ""):
        await self._send({
            "type": "tool_result", "name": name, "result": result,
            "is_error": is_error, "duration_ms": duration_ms, "id": tool_use_id,
        })

    async def on_response_done(self, raw: dict):
        await self._send({"type": "response_done", "raw": raw})

    async def on_done(self, final_text: str):
        await self._send({"type": "done", "final_text": final_text})

    async def on_error(self, message: str):
        await self._send({"type": "error", "message": message})

    async def on_compact_call(self, old_msg_count: int, pre_tokens: int):
        await self._send({
            "type": "compact_call", "old_msg_count": old_msg_count, "pre_tokens": pre_tokens,
        })

    async def on_compact(self, pre_tokens: int, post_tokens: int,
                         trigger: str, summary: str = ""):
        await self._send({
            "type": "compact", "pre_tokens": pre_tokens, "post_tokens": post_tokens,
            "trigger": trigger, "summary": summary,
        })

    async def on_snip(self, groups_removed: int, tokens_before: int, tokens_after: int):
        await self._send({
            "type": "snip", "groups_removed": groups_removed,
            "tokens_before": tokens_before, "tokens_after": tokens_after,
        })

    async def on_subagent_done(self, agent_id: str, status: str, result: str):
        await self._send({
            "type": "subagent_done", "agent_id": agent_id,
            "status": status, "result": result,
        })

    async def on_request(self, text: str, msg_count: int, est_tokens: int,
                         tools_count: int, model: str = ""):
        await self._send({
            "type": "request", "text": text, "msg_count": msg_count,
            "est_tokens": est_tokens, "tools_count": tools_count, "model": model,
        })

    async def on_enqueued(self, from_name: str, message: str, source: str):
        await self._send({
            "type": "enqueued", "from_name": from_name, "message": message, "source": source,
        })


async def _handle_client(websocket: ServerConnection, controller: AgentController):
    """Handle a single WebSocket client connection."""
    handler = WsEventHandler(websocket)
    controller.handler = handler

    await websocket.send(json.dumps({
        "type": "connected", "version": "0.1.0",
    }))

    async for raw_message in websocket:
        try:
            msg = json.loads(raw_message)
        except json.JSONDecodeError:
            await websocket.send(json.dumps({
                "type": "error", "message": "Invalid JSON",
            }))
            continue

        msg_type = msg.get("type", "")
        try:
            if msg_type == "send_message":
                await controller.send_message(msg.get("text", ""))
            elif msg_type == "cancel":
                await controller.cancel()
            elif msg_type == "clear_history":
                controller.clear_history()
            elif msg_type == "reconfigure":
                new_config = AgentConfig(**msg.get("config", {}))
                controller.reconfigure(new_config)
            elif msg_type == "get_status":
                await websocket.send(json.dumps({
                    "type": "status",
                    "busy": controller.agent._loop_running,
                    "config": {
                        "provider": controller.config.provider,
                        "model": controller.provider.model,
                    },
                    "usage": controller.estimate_usage(),
                }, ensure_ascii=False))
            elif msg_type == "shutdown":
                break
        except Exception as e:
            await websocket.send(json.dumps({
                "type": "error", "message": str(e),
            }, ensure_ascii=False))


async def run_ws_server(config: AgentConfig, port: int = 18765):
    """Start WebSocket server. Called from main.py --ws mode."""

    # Create a controller with a placeholder handler (will be replaced on connect)
    placeholder_handler = EventHandler()
    controller = AgentController(config, placeholder_handler)
    await controller.connect_mcp()

    # 单客户端：只接受一个连接
    async def handler(websocket):
        await _handle_client(websocket, controller)

    logger.info(f"WebSocket server listening on ws://127.0.0.1:{port}")
    async with serve(handler, "127.0.0.1", port):
        await asyncio.Future()  # run forever
```

- [ ] **Step 2: Commit**

```bash
git add agentcore/ws_server.py requirements.txt
git commit -m "feat: add WebSocket server for frontend communication"
```

---

### Task 2.2: 添加 pytest 测试 ws_server 协议

**文件:**
- Create: `agentcore/tests/test_ws_server.py`

- [ ] **Step 1: 创建测试文件**

```python
"""Test WebSocket server protocol without needing a frontend."""

import json
import pytest
import websockets


@pytest.mark.asyncio
async def test_connected_event():
    """连接后立即收到 connected 事件。"""
    async with websockets.connect("ws://127.0.0.1:18765") as ws:
        raw = await ws.recv()
        msg = json.loads(raw)
        assert msg["type"] == "connected"
        assert "version" in msg


@pytest.mark.asyncio
async def test_send_message_triggers_thinking():
    """发送消息后应该收到 thinking 事件。"""
    async with websockets.connect("ws://127.0.0.1:18765") as ws:
        await ws.recv()  # skip connected
        await ws.send(json.dumps({"type": "send_message", "text": "Hello"}))
        # 应该收到 thinking 或 text_delta 事件
        raw = await ws.recv()
        msg = json.loads(raw)
        assert msg["type"] in ("thinking", "text_delta", "error")


@pytest.mark.asyncio
async def test_invalid_json_returns_error():
    """收到非法 JSON 时返回 error。"""
    async with websockets.connect("ws://127.0.0.1:18765") as ws:
        await ws.recv()  # skip connected
        await ws.send("not json{")
        raw = await ws.recv()
        msg = json.loads(raw)
        assert msg["type"] == "error"


@pytest.mark.asyncio
async def test_get_status():
    """get_status 返回当前状态。"""
    async with websockets.connect("ws://127.0.0.1:18765") as ws:
        await ws.recv()  # skip connected
        await ws.send(json.dumps({"type": "get_status"}))
        raw = await ws.recv()
        msg = json.loads(raw)
        assert msg["type"] == "status"
        assert "busy" in msg
        assert "config" in msg
        assert "usage" in msg
```

- [ ] **Step 2: 启动后端并运行测试**

```bash
# 终端 1: 启动后端
python main.py --ws --port 18765 &

# 终端 2: 运行测试
python -m pytest agentcore/tests/test_ws_server.py -v

# 停止后端
kill %1
```

Expected: 测试通过（至少 connected 和 get_status 通过）。

- [ ] **Step 3: Commit**

```bash
git add agentcore/tests/test_ws_server.py
git commit -m "test: add WebSocket protocol tests"
```

---

## Phase 3: Vue 3 前端脚手架

### Task 3.1: 用 Vite 初始化 Vue 3 + TypeScript 项目

- [ ] **Step 1: 创建前端项目**

```bash
npm create vite@latest ui -- --template vue-ts
cd ui
npm install
```

- [ ] **Step 2: 安装依赖**

```bash
cd ui
npm install pinia
npm install marked  # 可选：Markdown 渲染（或用 markdown-it）
```

- [ ] **Step 3: 创建目录结构**

```bash
cd ui
mkdir -p src/components src/stores src/services src/views
rm -f src/components/HelloWorld.vue
rm -f src/assets/vue.svg
```

- [ ] **Step 4: 创建 `ui/src/services/agentWs.ts`**

```typescript
// WebSocket 客户端，封装连接、自动重连、事件分发

type EventCallback = (data: any) => void;

class AgentWsService {
  private ws: WebSocket | null = null;
  private url: string;
  private listeners: Map<string, Set<EventCallback>> = new Map();
  private reconnectTimer: number | null = null;
  private reconnectDelay = 1000;

  constructor(url: string = 'ws://127.0.0.1:18765') {
    this.url = url;
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    this.ws = new WebSocket(this.url);
    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        this.dispatch(msg.type, msg);
      } catch {
        // ignore parse errors
      }
    };

    this.ws.onclose = () => {
      this.scheduleReconnect();
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30000);
      this.connect();
    }, this.reconnectDelay);
  }

  private dispatch(type: string, data: any): void {
    this.reconnectDelay = 1000; // reset on success
    const cbs = this.listeners.get(type);
    if (cbs) {
      cbs.forEach(fn => fn(data));
    }
  }

  on(event: string, callback: EventCallback): void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(callback);
  }

  off(event: string, callback: EventCallback): void {
    this.listeners.get(event)?.delete(callback);
  }

  send(data: Record<string, any>): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }
}

export const agentWs = new AgentWsService();
```

- [ ] **Step 5: 创建 `ui/src/stores/chat.ts`**

```typescript
import { ref } from 'vue';
import { defineStore } from 'pinia';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: ToolCallEntry[];
  thinking?: boolean;
}

interface ToolCallEntry {
  name: string;
  preview: string;
  result?: string;
  isError?: boolean;
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([]);
  const thinking = ref(false);
  const currentAssistantMsg = ref('');

  function addUserMessage(text: string) {
    messages.value.push({ role: 'user', content: text });
    currentAssistantMsg.value = '';
  }

  function startThinking() {
    thinking.value = true;
  }

  function appendToken(token: string) {
    if (thinking.value) {
      thinking.value = false;
    }
    currentAssistantMsg.value += token;
  }

  function finalizeAssistantMessage() {
    if (currentAssistantMsg.value) {
      messages.value.push({
        role: 'assistant',
        content: currentAssistantMsg.value,
      });
      currentAssistantMsg.value = '';
    }
  }

  function addToolCall(name: string, preview: string) {
    // Append tool call to current assistant message
    // ...
  }

  function clear() {
    messages.value = [];
    currentAssistantMsg.value = '';
    thinking.value = false;
  }

  return {
    messages, thinking, currentAssistantMsg,
    addUserMessage, startThinking, appendToken, finalizeAssistantMessage,
    addToolCall, clear,
  };
});
```

- [ ] **Step 6: 创建 `ui/src/stores/agent.ts`**

```typescript
import { ref } from 'vue';
import { defineStore } from 'pinia';

export const useAgentStore = defineStore('agent', () => {
  const busy = ref(false);
  const provider = ref('');
  const model = ref('');

  function setFromStatus(data: any) {
    busy.value = data.busy;
    provider.value = data.config?.provider || '';
    model.value = data.config?.model || '';
  }

  return { busy, provider, model, setFromStatus };
});
```

- [ ] **Step 7: 创建 `ui/src/stores/debug.ts`**

```typescript
import { ref } from 'vue';
import { defineStore } from 'pinia';

interface DebugEntry {
  prefix: string;
  message: string;
  color: string;
  groupKey?: string;
  groupIdx?: number;
  opacity: number;
  data?: any;
}

export const useDebugStore = defineStore('debug', () => {
  const entries = ref<DebugEntry[]>([]);
  const usageProgress = ref(0);
  const usageText = ref('-- tokens');

  function addEvent(prefix: string, message: string, color: string, data?: any, groupKey?: string) {
    entries.value.push({
      prefix, message, color, groupKey, opacity: 1.0, data,
    });
    if (entries.value.length > 100) {
      entries.value = entries.value.slice(-100);
    }
  }

  function updateUsage(tokens: number, maxTokens: number) {
    usageProgress.value = Math.min(tokens / maxTokens, 1.0);
    usageText.value = `~${tokens} tokens (${Math.round(usageProgress.value * 100)}%)`;
  }

  function clear() {
    entries.value = [];
  }

  return { entries, usageProgress, usageText, addEvent, updateUsage, clear };
});
```

- [ ] **Step 8: Commit**

```bash
cd ui && git init && git add -A && git commit -m "feat: scaffold Vue 3 + Pinia project skeleton"
```

---

### Task 3.2: 创建主布局 App.vue

**文件:**
- Create/Modify: `ui/src/App.vue`

- [ ] **Step 1: 写主布局**

```vue
<template>
  <div class="app-layout">
    <header class="app-header">
      <span class="app-title">{{ provider }} / {{ model }}</span>
      <div class="header-actions">
        <button @click="showConfig = true">Config</button>
        <button @click="showDebug = !showDebug">Debug</button>
        <button @click="chatStore.clear()">Clear</button>
      </div>
    </header>

    <div class="app-body">
      <AgentSidebar v-if="showSidebar" />
      <ChatView class="chat-main" />
      <DebugDrawer v-if="showDebug" />
    </div>

    <InputBar class="app-input" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useChatStore } from './stores/chat';
import { useAgentStore } from './stores/agent';
import { useDebugStore } from './stores/debug';
import { agentWs } from './services/agentWs';
// import components
// import ChatView from './components/ChatView.vue';
// import InputBar from './components/InputBar.vue';
// import DebugDrawer from './components/DebugDrawer.vue';
// import AgentSidebar from './components/AgentSidebar.vue';

const chatStore = useChatStore();
const agentStore = useAgentStore();
const debugStore = useDebugStore();

const showDebug = ref(false);
const showSidebar = ref(false);
const showConfig = ref(false);

onMounted(() => {
  agentWs.on('connected', () => {
    agentWs.send({ type: 'get_status' });
  });

  agentWs.on('thinking', () => chatStore.startThinking());
  agentWs.on('text_delta', (d) => chatStore.appendToken(d.token));
  agentWs.on('tool_use', (d) => debugStore.addEvent('[Tool]', `${d.name}`, '#6366F1', d));
  agentWs.on('done', (d) => chatStore.finalizeAssistantMessage());
  agentWs.on('response_done', () => chatStore.finalizeAssistantMessage());
  agentWs.on('error', (d) => debugStore.addEvent('[Error]', d.message, '#EF4444'));
  agentWs.on('status', (d) => agentStore.setFromStatus(d));

  agentWs.connect();
});
</script>
```

- [ ] **Step 2: 写基础样式（全局 CSS）**

```bash
# 添加一个基础的全局样式文件 ui/src/style.css
```

```css
/* ui/src/style.css */
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; color: #1E1B3A; background: #FAFBFC; }

.app-layout { display: flex; flex-direction: column; height: 100vh; }
.app-header { display: flex; align-items: center; justify-content: space-between; padding: 0 16px; height: 40px; border-bottom: 1px solid #F1F3F6; background: white; }
.app-body { display: flex; flex: 1; overflow: hidden; }
.chat-main { flex: 1; overflow-y: auto; }
.app-input { border-top: 1px solid #F1F3F6; }
```

- [ ] **Step 3: Commit**

---

## Phase 4: Vue 组件实现

> 每个组件独立 Task，可并行开发。

### Task 4.1: ChatView + ChatBubble 组件

**文件:**
- Create: `ui/src/components/ChatView.vue`
- Create: `ui/src/components/ChatBubble.vue`

- [ ] **Step 1: ChatView.vue — 消息列表**

```vue
<template>
  <div class="chat-view" ref="container">
    <ChatBubble
      v-for="(msg, i) in chatStore.messages"
      :key="i"
      :message="msg"
    />
    <!-- Thinking 指示器 -->
    <div v-if="chatStore.thinking" class="thinking-row">
      <span class="dot"></span><span class="dot"></span><span class="dot"></span>
      <span class="thinking-text">思考中...</span>
    </div>
    <!-- 当前流式内容 -->
    <ChatBubble
      v-if="chatStore.currentAssistantMsg"
      :message="{ role: 'assistant', content: chatStore.currentAssistantMsg }"
      :streaming="true"
    />
  </div>
</template>

<script setup lang="ts">
import { watch, ref, nextTick } from 'vue';
import { useChatStore } from '../stores/chat';
import ChatBubble from './ChatBubble.vue';

const chatStore = useChatStore();
const container = ref<HTMLElement | null>(null);

watch(
  () => [chatStore.messages.length, chatStore.currentAssistantMsg],
  () => {
    nextTick(() => {
      if (container.value) {
        container.value.scrollTop = container.value.scrollHeight;
      }
    });
  }
);
</script>
```

- [ ] **Step 2: ChatBubble.vue — 用户/AI 气泡**

```vue
<template>
  <div :class="['bubble-row', message.role]">
    <div v-if="message.role === 'assistant'" class="avatar">AI</div>
    <div :class="['bubble', message.role]">
      <!-- Markdown 渲染 (简单版用 marked, 或直接用 v-html) -->
      <div v-html="renderedContent" class="bubble-content" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
// import { marked } from 'marked';  // 后续可替换为 marked

const props = defineProps<{
  message: { role: string; content: string };
  streaming?: boolean;
}>();

const renderedContent = computed(() => {
  // 简单实现：转义 HTML + 代码块识别
  // 后续可替换为 marked
  let text = props.message.content
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  // 代码块: ``` ... ```
  text = text.replace(/```(\w*)\n([\s\S]*?)```/g,
    '<pre><code>$2</code></pre>');
  // 行内代码: `...`
  text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
  // 加粗: **...**
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // 换行
  text = text.replace(/\n/g, '<br>');
  return text;
});
</script>

<style scoped>
.bubble-row {
  display: flex;
  padding: 8px 16px;
  gap: 8px;
}
.bubble-row.user { justify-content: flex-end; }
.bubble-row.assistant { justify-content: flex-start; align-items: flex-start; }
.avatar {
  width: 28px; height: 28px; border-radius: 14px;
  background: linear-gradient(135deg, #6366F1, #8B5CF6);
  color: white; display: flex; align-items: center; justify-content: center;
  font-size: 14px; font-weight: 600; flex-shrink: 0;
}
.bubble {
  max-width: 75%;
  padding: 8px 14px;
  border-radius: 14px;
  font-size: 16px;
  line-height: 1.5;
}
.bubble.user {
  background: #F1F3F6; border: 1px solid #EAEAEF;
  border-bottom-right-radius: 3px;
}
.bubble.assistant {
  background: #EBEEF2; border: 1px solid #DDE0E5;
  border-top-left-radius: 3px;
}
.bubble-content :deep(pre) {
  background: #f0f0f0; padding: 8px; border-radius: 6px;
  overflow-x: auto; font-family: Consolas, monospace; font-size: 15px;
}
.bubble-content :deep(code) {
  font-family: Consolas, monospace; font-size: 15px;
  background: #f0f0f0; padding: 1px 4px; border-radius: 3px;
}
.thinking-row { display: flex; gap: 4px; padding: 8px 16px; }
.dot { width: 6px; height: 6px; border-radius: 3px; background: #94A3B8; }
.thinking-text { font-size: 14px; color: #94A3B8; }
</style>
```

- [ ] **Step 3: Commit**

```bash
git add ui/src/components/ChatView.vue ui/src/components/ChatBubble.vue
git commit -m "feat: add ChatView and ChatBubble components"
```

---

### Task 4.2: InputBar 组件

**文件:**
- Create: `ui/src/components/InputBar.vue`

- [ ] **Step 1: InputBar.vue**

```vue
<template>
  <div class="input-bar">
    <div class="input-wrapper">
      <textarea
        v-model="text"
        class="input-field"
        rows="1"
        placeholder="输入消息... (Ctrl+Enter 发送)"
        @keydown="onKeydown"
      ></textarea>
    </div>
    <div class="input-buttons">
      <button v-if="agentStore.busy" class="btn-stop" @click="stop">■</button>
      <button class="btn-send" :disabled="agentStore.busy" @click="send">↑</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useAgentStore } from '../stores/agent';
import { useChatStore } from '../stores/chat';
import { agentWs } from '../services/agentWs';

const agentStore = useAgentStore();
const chatStore = useChatStore();
const text = ref('');

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    send();
  }
}

function send() {
  const msg = text.value.trim();
  if (!msg) return;
  chatStore.addUserMessage(msg);
  agentWs.send({ type: 'send_message', text: msg });
  text.value = '';
}

function stop() {
  agentWs.send({ type: 'cancel' });
}
</script>

<style scoped>
.input-bar { display: flex; align-items: flex-end; gap: 8px; padding: 10px 18px; background: #FAFBFC; border-top: 1px solid #F1F3F6; }
.input-wrapper { flex: 1; border: 1px solid #E2E6EC; border-radius: 10px; padding: 10px 14px; background: white; }
.input-field { width: 100%; border: none; outline: none; resize: none; font-size: 17px; color: #1E1B3A; font-family: inherit; }
.input-field::placeholder { color: #64748B; }
.input-buttons { display: flex; flex-direction: column; gap: 4px; }
.btn-send { width: 32px; height: 32px; border-radius: 9px; border: none; background: #6366F1; color: white; font-size: 16px; cursor: pointer; }
.btn-send:disabled { background: #A5B4FC; cursor: not-allowed; }
.btn-stop { width: 32px; height: 32px; border-radius: 9px; border: none; background: #EF4444; color: white; font-size: 14px; cursor: pointer; }
</style>
```

- [ ] **Step 2: Commit**

---

### Task 4.3: DebugDrawer 组件

**文件:**
- Create: `ui/src/components/DebugDrawer.vue`

- [ ] **Step 1: DebugDrawer.vue**

```vue
<template>
  <div class="debug-drawer" :style="{ width: (open ? '280px' : '36px') }">
    <div v-if="!open" class="collapsed" @click="open = true">
      <span>调</span><span>试</span>
      <div class="dot-indicator"></div>
    </div>
    <div v-else class="expanded">
      <div class="debug-header">
        <span>调试面板</span>
        <button @click="open = false">×</button>
      </div>
      <div class="usage-section">
        <span>上下文窗口</span>
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: (debugStore.usageProgress * 100) + '%' }"></div>
        </div>
        <span class="usage-text">{{ debugStore.usageText }}</span>
      </div>
      <div class="event-log">
        <div v-for="(entry, i) in debugStore.entries" :key="i"
             :class="['event-entry', entry.groupKey ? 'has-group' : '']"
             :style="{ opacity: entry.opacity }"
             @click="onEntryClick(entry)">
          <span class="event-prefix" :style="{ color: entry.color }">{{ entry.prefix }}</span>
          <span class="event-message">{{ entry.message }}</span>
        </div>
      </div>
      <div class="debug-footer">
        <button @click="debugStore.clear()" class="btn-clear">Clear History</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useDebugStore } from '../stores/debug';

const debugStore = useDebugStore();
const open = ref(false);

function onEntryClick(entry: any) {
  // 弹窗显示详细数据
  if (entry.data) {
    alert(JSON.stringify(entry.data, null, 2));
  }
}
</script>

<style scoped>
.debug-drawer { transition: width 0.2s ease-out; border-left: 1px solid #F1F3F6; overflow: hidden; background: #FAFBFC; }
.collapsed { display: flex; flex-direction: column; align-items: center; padding-top: 14px; cursor: pointer; }
.dot-indicator { width: 6px; height: 6px; border-radius: 3px; background: #E2E6EC; margin-top: 8px; }
.expanded { display: flex; flex-direction: column; height: 100%; padding: 12px; }
.debug-header { display: flex; justify-content: space-between; margin-bottom: 8px; }
.usage-section { margin-bottom: 10px; font-size: 14px; color: #64748B; }
.progress-bar { height: 6px; background: #E8E8EF; border-radius: 3px; margin: 4px 0; }
.progress-fill { height: 100%; background: #6366F1; border-radius: 3px; transition: width 0.3s; }
.event-log { flex: 1; overflow-y: auto; background: #F8F9FB; border-radius: 6px; padding: 8px; border: 1px solid #EEF0F4; }
.event-entry { padding: 2px 4px; border-bottom: 1px solid #E8EAF0; cursor: default; font-size: 13px; }
.event-prefix { font-weight: 600; margin-right: 4px; }
.debug-footer { margin-top: 8px; }
.btn-clear { font-size: 14px; color: #EF4444; background: none; border: none; cursor: pointer; }
</style>
```

- [ ] **Step 2: Commit**

---

### Task 4.4: DiffViewer 组件

**文件:**
- Create: `ui/src/components/DiffViewer.vue`

- [ ] **Step 1: DiffViewer.vue**

```vue
<template>
  <div class="diff-viewer">
    <div class="diff-header" @click="open = !open">
      <span class="arrow">{{ open ? '▼' : '▶' }}</span>
      <span class="filename">{{ filename }}</span>
      <span class="summary">+{{ added }} -{{ removed }}</span>
    </div>
    <div v-if="open" class="diff-body">
      <button class="expand-all" @click="expandAll">Expand All</button>
      <div class="diff-lines" ref="diffLinesRef">
        <div v-for="block in displayBlocks" :key="block.key" class="diff-block">
          <div v-if="block.type === 'fold'" class="fold-row" @click="() => unfold(block.key)">
            {{ block.count }} lines unchanged
          </div>
          <div v-else v-for="line in block.lines" :key="line.key" class="diff-line-row">
            <div :class="['left-side', line.leftClass]">
              <span class="line-num">{{ line.ln }}</span><span class="spacer"></span>
              <span class="line-text">{{ line.lt }}</span>
            </div>
            <div :class="['right-side', line.rightClass]">
              <span class="line-num">{{ line.rn }}</span><span class="spacer"></span>
              <span class="line-text">{{ line.rt }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';

const props = defineProps<{
  filePath: string;
  oldContent: string;
  newContent: string;
}>();

const open = ref(true);

// 简化版 diff：用 JS 实现基本的行比较
// 注：真正的 diff 算法应该用后端返回或 difflib 的 JS 实现
const filename = computed(() => props.filePath.replace(/\\/g, '/').split('/').pop() || '');
const added = ref(0);
const removed = ref(0);

// FIXME: Phase 5 用真正的 JavaScript diff 库实现
const displayBlocks = ref<any[]>([]);

function expandAll() {}
function unfold(key: any) {}
</script>
```

DiffViewer 需要 JavaScript 的 diff 库。**真正的实现放到 Phase 5 用 `diff` npm 包完成。**

- [ ] **Step 2: Commit**（暂存骨架）

---

### Task 4.5: AgentSidebar, ConfigDialog, McpDialog, SkillDialog 组件

**文件:**
- Create: `ui/src/components/AgentSidebar.vue`
- Create: `ui/src/components/ConfigDialog.vue`
- Create: `ui/src/components/McpDialog.vue`
- Create: `ui/src/components/SkillDialog.vue`

- [ ] **Step 1: 创建各组件骨架**

每个组件先写结构和样式，功能通过 WebSocket 连上后再补充。

```vue
<!-- AgentSidebar.vue -->
<template>
  <div class="agent-sidebar">
    <h3>Agents</h3>
    <div v-for="agent in agents" :key="agent.id" class="agent-item">
      <span>{{ agent.name }}</span>
      <span :class="['status', agent.status]"></span>
    </div>
  </div>
</template>
```

```vue
<!-- ConfigDialog.vue -->
<template>
  <dialog open>
    <h3>配置</h3>
    <label>Provider: <input v-model="provider" /></label>
    <label>API Key: <input v-model="apiKey" type="password" /></label>
    <button @click="save">Save</button><button @click="$emit('close')">Cancel</button>
  </dialog>
</template>
```

```vue
<!-- McpDialog.vue -->
<template>
  <dialog open>
    <h3>MCP Servers</h3>
    <div v-for="s in servers" :key="s.name">{{ s.name }} ({{ s.tool_count }} tools)</div>
    <button @click="$emit('close')">Close</button>
  </dialog>
</template>
```

```vue
<!-- SkillDialog.vue -->
<template>
  <dialog open>
    <h3>Skills</h3>
    <div v-for="s in skills" :key="s.name">{{ s.name }}</div>
    <button @click="$emit('close')">Close</button>
  </dialog>
</template>
```

- [ ] **Step 2: Commit**

```bash
git add ui/src/components/AgentSidebar.vue ui/src/components/ConfigDialog.vue ui/src/components/McpDialog.vue ui/src/components/SkillDialog.vue
git commit -m "feat: add AgentSidebar, ConfigDialog, McpDialog, SkillDialog skeletons"
```

---

## Phase 5: Electron Shell

### Task 5.1: 添加 Electron 配置

- [ ] **Step 1: 安装 Electron 依赖**

```bash
cd ui
npm install --save-dev electron electron-builder
```

- [ ] **Step 2: 创建 `ui/electron/main.ts`**

```typescript
import { app, BrowserWindow, dialog, Menu, spawn } from 'electron';
import * as path from 'path';
import { ChildProcess } from 'child_process';

let mainWindow: BrowserWindow | null = null;
let pythonProcess: ChildProcess | null = null;
let restartCount = 0;

const isDev = !app.isPackaged;
const PYTHON_PORT = 18765;

function getAssetPath(filename: string): string {
  if (isDev) return path.join(__dirname, '..', filename);
  return path.join(process.resourcesPath!, filename);
}

function startPythonBackend(): void {
  if (pythonProcess) return;

  const pythonCmd = isDev ? 'python' : getAssetPath('agentcore.exe');
  const args = isDev
    ? ['agentcore/main.py', '--ws', '--port', String(PYTHON_PORT)]
    : ['--ws', '--port', String(PYTHON_PORT)];

  pythonProcess = spawn(pythonCmd, args);

  pythonProcess.stdout?.on('data', (data: Buffer) => {
    console.log(`[python] ${data.toString()}`);
  });

  pythonProcess.stderr?.on('data', (data: Buffer) => {
    console.error(`[python] ${data.toString()}`);
  });

  pythonProcess.on('exit', (code: number | null) => {
    pythonProcess = null;
    if (code !== 0 && restartCount < 3) {
      restartCount++;
      setTimeout(startPythonBackend, 2000);
    } else {
      dialog.showErrorBox('Backend Error', 'Python backend crashed. Restart the application.');
    }
  });
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }
}

function buildMenu(): void {
  const template: Electron.MenuItemConstructorOptions[] = [
    {
      label: 'Agent',
      submenu: [
        {
          label: 'Restart Backend',
          click: () => {
            pythonProcess?.kill();
            restartCount = 0;
            startPythonBackend();
          },
        },
        { type: 'separator' },
        { label: 'Quit', role: 'quit' },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

app.whenReady().then(() => {
  buildMenu();
  startPythonBackend();
  createWindow();
});

app.on('window-all-closed', () => {
  pythonProcess?.kill();
  app.quit();
});
```

- [ ] **Step 3: 更新 `ui/package.json` 添加 scripts 和 build 配置**

```json
{
  "main": "dist-electron/main.js",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc && vite build",
    "electron:dev": "concurrently \"vite\" \"wait-on http://localhost:5173 && electron .\"",
    "electron:build": "vite build && electron-builder"
  },
  "build": {
    "appId": "com.ai-codeagent.app",
    "productName": "AI Code Agent",
    "extraResources": [{ "from": "agentcore.exe", "to": "" }],
    "win": { "target": "nsis" }
  }
}
```

- [ ] **Step 4: Commit**

```bash
git add ui/electron/ ui/package.json
git commit -m "feat: add Electron main process"
```

---

## Phase 6: 打包与完善

### Task 6.1: PyInstaller 配置

- [ ] **Step 1: 创建 PyInstaller spec 文件**

```bash
# 在项目根目录
pip install pyinstaller
pyi-makespec --name agentcore --onefile agentcore/main.py --add-data "config.yaml:." --hidden-import agentcore.ws_server
```

- [ ] **Step 2: 构建 Python exe**

```bash
pyinstaller agentcore.spec --distpath build/
```

Expected: `build/agentcore.exe` 生成。

- [ ] **Step 3: Commit**

---

### Task 6.2: electron-builder 打包

- [ ] **Step 1: 完整构建**

```bash
cd ui
npm run electron:build
```

Expected: `ui/release/` 下生成安装包。

- [ ] **Step 2: Commit**

---

### Task 6.3: DiffViewer 完善

- [ ] **Step 1: 安装 diff 库**

```bash
cd ui
npm install diff
npm install --save-dev @types/diff
```

- [ ] **Step 2: 实现真正的 diff 算法**

在 `DiffViewer.vue` 中用 `diff` 库实现与 Python 端 `_diff_blocks` 等价的逻辑。

- [ ] **Step 3: Commit**

---

### Task 6.4: 整体集成测试

- [ ] **Step 1: 启动后端并测试前端**

```bash
# 终端 1
python main.py --ws --port 18765

# 终端 2
cd ui && npm run dev
# 打开 http://localhost:5173，测试发送消息、接收响应、工具调用、取消等
```

- [ ] **Step 2: 运行所有测试**

```bash
python -m pytest agentcore/tests/ -v
cd ui && npx vitest run
```

- [ ] **Step 3: Commit 最终修复**

---

## 自检清单

- [ ] 所有 13 个 EventHandler 事件类型都在 ws_server.py 中实现
- [ ] Vue 组件列表覆盖所有 Flet 组件（9 个）
- [ ] import 变更覆盖所有 42 个文件
- [ ] 无 "TBD" / "TODO" 占位符
- [ ] TUI 模式向后兼容（`python main.py -s / -c`）
