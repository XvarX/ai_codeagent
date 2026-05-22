# Flet 迁移 + 前后端分离 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将桌面 UI 从 PySide6 迁移到 Flet，引入 AgentController 实现前后端分离，终端/命令行模式不变。

**Architecture:** 新增 `controller.py` 封装 Agent 生命周期（内部调用 `agent.run_stream()`），新增 `flet_ui/` 目录含 5 个组件文件，`main.py` 默认模式改为启动 Flet，删除 `qt_ui/`。Agent/Provider/Tools/Compact 层不变。

**Tech Stack:** Python 3.13, Flet >= 0.25, asyncio, markdown-it-py (保留)

---

### Task 1: run_stream() 集成 compact 管线

**Files:**
- Modify: `agent.py:217-321`

**Purpose:** run_stream() 目前缺少 compact 管线（history snip → micro compact → auto compact），导致长对话不会自动压缩。与 run() 对齐。

- [ ] **Step 1: 在 run_stream() while 循环顶部添加 compact 管线**

在 `agent.py` 的 `run_stream()` 方法中，将 while 循环体开头的简单 snip 替换为完整的 compact 管线（与 `run()` 方法第 63-100 行一致）。

定位到 `agent.py` 第 227-231 行：
```python
            turn_count += 1

            if len(self.messages) > self.max_messages:
                self.messages = self.messages[-self.max_messages:]
```

替换为：
```python
            turn_count += 1

            # ── Compaction Pipeline (mirrors run()) ──────────
            if len(self.messages) > self.max_messages:
                self.messages = self.messages[-self.max_messages:]

            if turn_count > 1:
                from compact.microCompact import micro_compact
                micro_compact(self.messages)

            from compact.autoCompact import should_auto_compact
            if should_auto_compact(
                self.messages,
                getattr(self.provider, 'model', None),
                actual_base=self._last_actual_tokens,
            ):
                from compact.compact import compact_conversation
                pre_tokens = self._est_tokens()
                try:
                    result = await compact_conversation(
                        self.provider, self.messages,
                        self.registry.get_schemas(),
                        keep_recent_rounds=2,
                    )
                    self.messages = result.summary_messages + result.messages_to_keep
                    self._last_actual_tokens = result.post_tokens
                    self._compact_count += 1

                    yield CompactEvent(
                        pre_tokens=pre_tokens,
                        post_tokens=result.post_tokens,
                        trigger=f"auto (#{self._compact_count})",
                    )
                except Exception:
                    pass
```

- [ ] **Step 2: 在 events.py 中添加 CompactEvent**

`events.py` 缺少 compact 事件类型。在文件末尾添加：

```python
@dataclass
class CompactEvent:
    """上下文压缩完成"""
    pre_tokens: int
    post_tokens: int
    trigger: str = ""
```

- [ ] **Step 3: 更新 agent.py 的 events import**

`agent.py` 第 219-221 行的 events import 添加 `CompactEvent`：

```python
        from events import (
            ThinkingEvent, TextDeltaEvent, ToolUseEvent, ToolDoneEvent,
            ResponseDoneEvent, DoneEvent, ErrorEvent, CompactEvent,
        )
```

- [ ] **Step 4: 在 run_stream() 的 ResponseDoneEvent 之后更新实际 token 用量**

在 `agent.py` 中 `yield ResponseDoneEvent` 对应的 `ResponseDoneEvent` 处理之后，添加与 `run()` 第 152-157 行相同的 token 追踪：

找到 `run_stream()` 中处理 `ResponseDoneEvent` 的 yield 之后（约第 262 行），在 `assistant_msg` 构建之前添加：

```python
                    elif isinstance(event, ResponseDoneEvent):
                        # Track actual token usage
                        usage = event.raw.get("usage", {})
                        if usage.get("total_tokens"):
                            self._last_actual_tokens = usage["total_tokens"]
                        elif usage.get("input_tokens"):
                            self._last_actual_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                        yield event
```

- [ ] **Step 5: 验证 agent.py 语法正确**

```bash
python -c "from agent import Agent; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add agent.py events.py
git commit -m "feat: run_stream() 集成 compact 管线，新增 CompactEvent

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: controller.py — AgentController + EventHandler

**Files:**
- Create: `controller.py`

**Purpose:** 封装 Agent 生命周期，框架无关。UI 层只依赖 AgentController，不直接接触 Agent/Provider/ToolRegistry。

- [ ] **Step 1: 创建 controller.py**

```python
"""AgentController — framework-agnostic Agent lifecycle wrapper."""

import asyncio
import json
from pathlib import Path

from config import AgentConfig
from tools.registry import ToolRegistry
from tools.bash import BashTool
from tools.file_read import FileReadTool
from tools.file_edit import FileEditTool
from tools.file_write import FileWriteTool
from tools.glob import GlobTool
from tools.grep import GrepTool
from providers.anthropic import AnthropicProvider
from providers.openai_compat import OpenAICompatProvider
from agent import Agent
from events import (
    ThinkingEvent, TextDeltaEvent, ToolUseEvent, ToolDoneEvent,
    ResponseDoneEvent, DoneEvent, ErrorEvent, CompactEvent,
)


def _build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register_all([
        BashTool(), FileReadTool(), FileEditTool(),
        FileWriteTool(), GlobTool(), GrepTool(),
    ])
    return registry


def _build_provider(config: AgentConfig):
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


class EventHandler:
    """Base event handler — override methods in UI layer."""

    async def on_thinking(self): pass
    async def on_text_delta(self, token: str): pass
    async def on_tool_use(self, name: str, input_dict: dict): pass
    async def on_tool_result(self, name: str, result: str, is_error: bool): pass
    async def on_response_done(self, raw: dict): pass
    async def on_done(self, final_text: str): pass
    async def on_error(self, message: str): pass
    async def on_compact(self, pre_tokens: int, post_tokens: int, trigger: str): pass


class AgentController:
    """Framework-agnostic Agent lifecycle manager.

    Wraps Agent creation, run_stream() event dispatch, cancel, and reconfig.
    """

    def __init__(self, config: AgentConfig, event_handler: EventHandler):
        self.config = config
        self.handler = event_handler
        self._cancel_event = asyncio.Event()
        self._current_task: asyncio.Task | None = None

        self.registry = _build_registry()
        self.provider = _build_provider(config)
        self.agent = Agent(
            provider=self.provider,
            registry=self.registry,
            cwd=config.cwd,
            max_turns=config.max_turns,
            max_messages=config.max_messages,
        )

    async def send_message(self, text: str) -> None:
        self._cancel_event.clear()
        self._current_task = asyncio.current_task()

        try:
            async for event in self.agent.run_stream(text):
                if self._cancel_event.is_set():
                    break

                if isinstance(event, ThinkingEvent):
                    await self.handler.on_thinking()
                elif isinstance(event, TextDeltaEvent):
                    await self.handler.on_text_delta(event.token)
                elif isinstance(event, ToolUseEvent):
                    await self.handler.on_tool_use(event.tool_name, event.input)
                elif isinstance(event, ToolDoneEvent):
                    await self.handler.on_tool_result(
                        event.tool_name, event.result, event.is_error)
                elif isinstance(event, ResponseDoneEvent):
                    await self.handler.on_response_done(event.raw)
                elif isinstance(event, DoneEvent):
                    await self.handler.on_done(event.final_text)
                elif isinstance(event, ErrorEvent):
                    await self.handler.on_error(event.message)
                elif isinstance(event, CompactEvent):
                    await self.handler.on_compact(
                        event.pre_tokens, event.post_tokens, event.trigger)
        except asyncio.CancelledError:
            pass
        finally:
            self._current_task = None

    async def cancel(self) -> None:
        self._cancel_event.set()
        if self._current_task is not None:
            self._current_task.cancel()
            try:
                await self._current_task
            except asyncio.CancelledError:
                pass

    def clear_history(self) -> None:
        self.agent.messages.clear()

    def reconfigure(self, new_config: AgentConfig) -> None:
        self.config = new_config
        self.provider = _build_provider(new_config)
        self.agent.provider = self.provider
        self.agent.messages.clear()

    def estimate_usage(self) -> dict:
        return {
            "message_count": len(self.agent.messages),
            "estimated_tokens": self.agent._est_tokens(),
        }
```

- [ ] **Step 2: 验证 AgentController 导入正确**

```bash
python -c "from controller import AgentController, EventHandler; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add controller.py
git commit -m "feat: 新增 AgentController + EventHandler 封装 Agent 生命周期

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: flet_ui/__init__.py

**Files:**
- Create: `flet_ui/__init__.py`

- [ ] **Step 1: 创建包初始化文件**

```bash
mkdir -p flet_ui
```

```python
"""Flet UI for AI Code Agent."""
```

- [ ] **Step 2: Commit**

```bash
git add flet_ui/__init__.py
git commit -m "feat: 创建 flet_ui 包

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: flet_ui/chat_view.py — 聊天气泡列表

**Files:**
- Create: `flet_ui/chat_view.py`

- [ ] **Step 1: 创建 ChatView**

```python
"""Chat bubble list with Markdown rendering."""

import flet as ft


class ChatView(ft.ListView):
    """Scrollable chat message list."""

    def __init__(self):
        super().__init__()
        self.expand = True
        self.spacing = 10
        self.padding = ft.padding.symmetric(horizontal=18, vertical=14)
        self.auto_scroll = True
        self._thinking_row: ft.Row | None = None

    def add_user_message(self, text: str) -> None:
        bubble = ft.Container(
            content=ft.Text(text, size=12, color="#1E1B3A", selectable=True),
            bgcolor="#F1F3F6",
            border=ft.border.all(1, "#EAEAEF"),
            border_radius=ft.border_radius.only(
                top_left=15, top_right=15, bottom_left=15, bottom_right=3,
            ),
            padding=ft.padding.symmetric(horizontal=15, vertical=10),
            alignment=ft.alignment.center_right,
        )
        row = ft.Row([bubble], alignment=ft.MainAxisAlignment.END)
        self.controls.append(row)

    def add_assistant_message(self, markdown_text: str) -> None:
        avatar = ft.Container(
            content=ft.Text("AI", size=10, color="white", weight=ft.FontWeight.W_600),
            width=28, height=28,
            border_radius=14,
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_left,
                end=ft.alignment.bottom_right,
                colors=["#6366F1", "#8B5CF6"],
            ),
            alignment=ft.alignment.center,
            shadow=ft.BoxShadow(
                blur_radius=4, color=ft.colors.with_opacity(0.25, "#6366F1"),
                offset=ft.Offset(0, 1),
            ),
        )
        bubble = ft.Container(
            content=ft.Markdown(
                markdown_text,
                selectable=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                code_theme="atom-one-light",
                code_style=ft.TextStyle(
                    size=11, font_family="monospace",
                ),
                auto_follow_links=True,
            ),
            bgcolor="#FAFBFC",
            border=ft.border.all(1, "#EEF0F4"),
            border_radius=ft.border_radius.only(
                top_left=3, top_right=15, bottom_left=15, bottom_right=15,
            ),
            padding=ft.padding.symmetric(horizontal=15, vertical=10),
        )
        row = ft.Row(
            [avatar, bubble],
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
        self.controls.append(row)

    def add_tool_label(self, name: str, preview: str) -> None:
        label = ft.Container(
            content=ft.Text(
                f"{name}  {preview}",
                size=10, color="#64748B",
            ),
            bgcolor="#F8F9FB",
            border=ft.border.all(1, "#EEF0F4"),
            border_radius=6,
            padding=ft.padding.symmetric(horizontal=9, vertical=3),
        )
        row = ft.Row([label], alignment=ft.MainAxisAlignment.START)
        self.controls.append(row)

    def show_thinking(self) -> None:
        if self._thinking_row is not None:
            return
        dots = ft.Row(
            [
                ft.Container(width=6, height=6, border_radius=3,
                             bgcolor="#A0A0B8", animate_opacity=ft.Animation(600, "ease")),
                ft.Container(width=6, height=6, border_radius=3,
                             bgcolor="#A0A0B8", animate_opacity=ft.Animation(600, "ease")),
                ft.Container(width=6, height=6, border_radius=3,
                             bgcolor="#A0A0B8", animate_opacity=ft.Animation(600, "ease")),
            ],
            spacing=4,
        )
        label = ft.Text("思考中...", size=10, color="#A0A0B8")
        self._thinking_row = ft.Row(
            [dots, label], spacing=6,
            alignment=ft.MainAxisAlignment.START,
        )
        self.controls.append(self._thinking_row)

    def hide_thinking(self) -> None:
        if self._thinking_row is not None:
            self.controls.remove(self._thinking_row)
            self._thinking_row = None

    def clear(self) -> None:
        self._thinking_row = None
        self.controls.clear()
```

- [ ] **Step 2: 验证导入**

```bash
python -c "from flet_ui.chat_view import ChatView; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add flet_ui/chat_view.py
git commit -m "feat: 新增 Flet ChatView 聊天气泡组件

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: flet_ui/input_bar.py — 底部输入栏

**Files:**
- Create: `flet_ui/input_bar.py`

- [ ] **Step 1: 创建 InputBar**

```python
"""Bottom input bar with text field and send button."""

import flet as ft


class InputBar(ft.Container):
    """Multi-line input with send button."""

    send_clicked: ft.ControlEvent | None = None

    def __init__(self, on_send=None):
        super().__init__()
        self._on_send_callback = on_send

        self._text_field = ft.TextField(
            hint_text="输入消息... (Ctrl+Enter 发送)",
            hint_style=ft.TextStyle(size=12, color="#94A3B8"),
            text_style=ft.TextStyle(size=12, color="#1E1B3A"),
            multiline=True,
            shift_enter=True,
            min_lines=1,
            max_lines=6,
            border=ft.InputBorder.NONE,
            expand=True,
            bgcolor="transparent",
            content_padding=ft.padding.symmetric(horizontal=4, vertical=4),
        )

        self._send_button = ft.IconButton(
            icon=ft.icons.SEND,
            icon_size=16,
            bgcolor="#6366F1",
            icon_color="white",
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=9),
                padding=ft.padding.all(8),
            ),
        )

        self.content = ft.Row(
            [
                ft.Container(
                    content=self._text_field,
                    border=ft.border.all(1, "#E2E6EC"),
                    border_radius=10,
                    padding=ft.padding.symmetric(horizontal=14, vertical=9),
                    expand=True,
                    bgcolor="#FFFFFF",
                ),
                self._send_button,
            ],
            spacing=8,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.END,
        )

        self.bgcolor = "#FAFBFC"
        self.border = ft.border.only(top=ft.BorderSide(1, "#F1F3F6"))
        self.padding = ft.padding.symmetric(horizontal=18, vertical=10)

        self._send_button.on_click = self._on_send_click

    def _on_send_click(self, e):
        text = self._text_field.value.strip()
        if text and self._on_send_callback:
            self._on_send_callback(text)
            self._text_field.value = ""
            self._text_field.update()

    @property
    def on_send(self):
        return self._on_send_callback

    @on_send.setter
    def on_send(self, callback):
        self._on_send_callback = callback

    def set_busy(self, busy: bool) -> None:
        self._send_button.disabled = busy
        self._send_button.bgcolor = "#A5B4FC" if busy else "#6366F1"
        self._send_button.update()
```

- [ ] **Step 2: 验证导入**

```bash
python -c "from flet_ui.input_bar import InputBar; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add flet_ui/input_bar.py
git commit -m "feat: 新增 Flet InputBar 底部输入栏组件

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: flet_ui/debug_drawer.py — 可折叠调试抽屉

**Files:**
- Create: `flet_ui/debug_drawer.py`

- [ ] **Step 1: 创建 DebugDrawer**

```python
"""Collapsible debug drawer with context usage and event log."""

import flet as ft


class DebugDrawer(ft.AnimatedContainer):
    """Right-side debug panel with expand/collapse animation."""

    def __init__(self, on_compact=None, on_clear=None):
        super().__init__()
        self._on_compact = on_compact
        self._on_clear = on_clear
        self._is_open = False
        self._event_count = 0

        # Collapsed state
        self.width = 36
        self.bgcolor = "#FAFBFC"
        self.border = ft.border.only(left=ft.BorderSide(1, "#F1F3F6"))
        self.animate = ft.Animation(200, ft.AnimationCurve.EASE_OUT)
        self.padding = ft.padding.all(0)

        # Collapsed content
        self._collapsed_view = ft.Container(
            content=ft.Column([
                ft.Container(height=12),
                ft.Text("调", size=10, color="#94A3B8", text_align=ft.TextAlign.CENTER),
                ft.Text("试", size=10, color="#94A3B8", text_align=ft.TextAlign.CENTER),
                ft.Container(
                    width=6, height=6, border_radius=3,
                    bgcolor="#E2E6EC",
                    alignment=ft.alignment.center,
                ),
            ], alignment=ft.MainAxisAlignment.START, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.symmetric(vertical=14),
            on_click=self._toggle,
        )

        # Expanded content
        self._title_bar = ft.Row([
            ft.Text("调试面板", size=12, weight=ft.FontWeight.W_600, color="#1E1B3A"),
            ft.IconButton(
                icon=ft.icons.CLOSE, icon_size=14,
                icon_color="#94A3B8",
                on_click=self._toggle,
            ),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        self._usage_bar = ft.ProgressBar(
            value=0, color="#6366F1", bgcolor="#E8E8EF",
            bar_height=6,
        )
        self._usage_text = ft.Text("-- tokens", size=10, color="#94A3B8")

        self._event_log = ft.ListView(
            spacing=2,
            padding=ft.padding.only(top=4),
            auto_scroll=True,
        )

        self._compact_btn = ft.TextButton(
            text="Compact", style=ft.ButtonStyle(
                color="#64748B", text_style=ft.TextStyle(size=10),
                padding=ft.padding.symmetric(horizontal=10, vertical=4),
            ),
            on_click=lambda e: self._on_compact and self._on_compact(),
        )
        self._clear_btn = ft.TextButton(
            text="Clear History", style=ft.ButtonStyle(
                color="#EF4444", text_style=ft.TextStyle(size=10),
                padding=ft.padding.symmetric(horizontal=10, vertical=4),
            ),
            on_click=lambda e: self._on_clear and self._on_clear(),
        )

        self._expanded_view = ft.Column([
            self._title_bar,
            ft.Divider(height=1, color="#EEF0F4"),
            ft.Container(height=6),
            ft.Text("上下文窗口", size=10, color="#94A3B8"),
            ft.Container(height=4),
            self._usage_bar,
            ft.Container(height=2),
            self._usage_text,
            ft.Container(height=10),
            ft.Text("事件日志", size=10, color="#94A3B8"),
            ft.Container(
                content=self._event_log,
                expand=True,
                bgcolor="#F8F9FB",
                border_radius=6,
                padding=ft.padding.all(8),
                border=ft.border.all(1, "#EEF0F4"),
            ),
            ft.Container(height=8),
            ft.Row([self._compact_btn, self._clear_btn],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ], spacing=0)

        self.content = self._collapsed_view

    def _toggle(self, e=None):
        if self._is_open:
            self.width = 36
            self._is_open = False
            self.content = self._collapsed_view
        else:
            self.width = 280
            self._is_open = True
            self.content = ft.Container(
                content=self._expanded_view,
                padding=ft.padding.all(12),
            )
            self._event_count = 0
        self.update()

    def add_event(self, prefix: str, message: str, color: str) -> None:
        self._event_count += 1
        if not self._is_open:
            # Pulse indicator
            self._update_pulse(True)
        entry = ft.Column([
            ft.Row([
                ft.Text(prefix, size=10, weight=ft.FontWeight.W_600, color=color),
            ]),
            ft.Text(message, size=9, color="#64748B", selectable=True,
                    max_lines=3, overflow=ft.TextOverflow.ELLIPSIS),
        ], spacing=1)
        self._event_log.controls.insert(0, entry)
        # Keep max 50 entries
        if len(self._event_log.controls) > 50:
            self._event_log.controls = self._event_log.controls[:50]
        if self._is_open:
            self._event_log.update()

    def _update_pulse(self, active: bool) -> None:
        # Update the collapse indicator dot color
        if hasattr(self, '_collapsed_view'):
            pass  # pulse handled via update cycle

    def update_context_usage(self, usage: dict) -> None:
        prompt = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0) or 0
        completion = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0) or 0
        total = usage.get("total_tokens", 0) or prompt + completion
        ratio = min(total / 100000, 1.0)
        self._usage_bar.value = ratio
        self._usage_text.value = f"~{total}  tokens  ({int(ratio * 100)}%)"
        if self._is_open:
            self._usage_bar.update()
            self._usage_text.update()

    def clear(self) -> None:
        self._event_log.controls.clear()
        if self._is_open:
            self._event_log.update()
```

- [ ] **Step 2: 验证导入**

```bash
python -c "from flet_ui.debug_drawer import DebugDrawer; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add flet_ui/debug_drawer.py
git commit -m "feat: 新增 Flet DebugDrawer 可折叠调试抽屉

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 7: flet_ui/config_dialog.py — 配置对话框

**Files:**
- Create: `flet_ui/config_dialog.py`

- [ ] **Step 1: 创建 ConfigDialog**

```python
"""LLM Provider configuration dialog."""

import flet as ft
import yaml
from pathlib import Path


CONFIG_PATH = Path("config.yaml")

PROVIDER_OPTIONS = [
    ft.dropdown.Option("anthropic", "Anthropic"),
    ft.dropdown.Option("openai", "OpenAI"),
    ft.dropdown.Option("glm", "GLM"),
    ft.dropdown.Option("deepseek", "DeepSeek"),
]


def show_config_dialog(page: ft.Page, on_save=None):
    """Open the LLM configuration dialog."""

    config = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    provider = config.get("provider", "glm")
    api_key = config.get("api_key", "")
    model = config.get("model", "")
    base_url = config.get("base_url", "")

    provider_dd = ft.Dropdown(
        value=provider,
        options=PROVIDER_OPTIONS,
        text_style=ft.TextStyle(size=12),
        border_color="#E2E6EC",
    )

    api_key_field = ft.TextField(
        value=api_key,
        label="API Key",
        label_style=ft.TextStyle(size=10),
        text_style=ft.TextStyle(size=12),
        password=True,
        can_reveal_password=True,
        border_color="#E2E6EC",
    )
    model_field = ft.TextField(
        value=model,
        label="Model",
        label_style=ft.TextStyle(size=10),
        text_style=ft.TextStyle(size=12),
        border_color="#E2E6EC",
    )
    base_url_field = ft.TextField(
        value=base_url,
        label="Base URL (optional)",
        label_style=ft.TextStyle(size=10),
        text_style=ft.TextStyle(size=12),
        border_color="#E2E6EC",
    )

    status_text = ft.Text("", size=10, color="#EF4444")

    def save_click(e):
        new_config = {
            "provider": provider_dd.value,
            "api_key": api_key_field.value,
            "model": model_field.value,
            "base_url": base_url_field.value,
        }
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.dump(new_config, f, allow_unicode=True, default_flow_style=False)
            from config import AgentConfig
            updated_config = AgentConfig.from_yaml()
            if on_save:
                on_save(updated_config)
            page.close(dlg)
        except Exception as ex:
            status_text.value = f"Save failed: {ex}"
            status_text.update()

    dlg = ft.AlertDialog(
        title=ft.Text("LLM 配置", size=14, weight=ft.FontWeight.W_600),
        content=ft.Column([
            ft.Text("Provider", size=10, color="#94A3B8"),
            provider_dd,
            ft.Container(height=8),
            api_key_field,
            ft.Container(height=8),
            model_field,
            ft.Container(height=8),
            base_url_field,
            ft.Container(height=4),
            status_text,
        ], height=320, width=360),
        actions=[
            ft.TextButton("取消", on_click=lambda e: page.close(dlg),
                         style=ft.ButtonStyle(color="#94A3B8")),
            ft.TextButton("保存", on_click=save_click,
                         style=ft.ButtonStyle(color="#6366F1")),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        shape=ft.RoundedRectangleBorder(radius=10),
    )

    page.open(dlg)
```

- [ ] **Step 2: 验证导入**

```bash
python -c "from flet_ui.config_dialog import show_config_dialog; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add flet_ui/config_dialog.py
git commit -m "feat: 新增 Flet ConfigDialog 配置对话框

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 8: flet_ui/app.py — Flet 主应用组装

**Files:**
- Create: `flet_ui/app.py`

- [ ] **Step 1: 创建 app.py 主入口**

```python
"""Flet main app — assembles ChatView, InputBar, DebugDrawer, and AgentController."""

import json
from pathlib import Path
from datetime import datetime

import flet as ft

from config import AgentConfig
from controller import AgentController, EventHandler
from flet_ui.chat_view import ChatView
from flet_ui.input_bar import InputBar
from flet_ui.debug_drawer import DebugDrawer
from flet_ui.config_dialog import show_config_dialog


class _FletEventHandler(EventHandler):
    """Bridge from AgentController events to Flet UI updates."""

    def __init__(self, app: "FletApp"):
        self.app = app

    async def on_thinking(self):
        self.app._on_thinking()

    async def on_text_delta(self, token: str):
        self.app._on_text_delta(token)

    async def on_tool_use(self, name: str, input_dict: dict):
        self.app._on_tool_use(name, input_dict)

    async def on_tool_result(self, name: str, result: str, is_error: bool):
        self.app._on_tool_result(name, result, is_error)

    async def on_response_done(self, raw: dict):
        self.app._on_response_done(raw)

    async def on_done(self, final_text: str):
        self.app._on_done(final_text)

    async def on_error(self, message: str):
        self.app._on_error(message)

    async def on_compact(self, pre_tokens: int, post_tokens: int, trigger: str):
        self.app._on_compact(pre_tokens, post_tokens, trigger)


class FletApp:
    """Main Flet application controller."""

    def __init__(self, page: ft.Page, config: AgentConfig):
        self.page = page
        self.config = config

        # Controller
        self.handler = _FletEventHandler(self)
        self.controller = AgentController(config, self.handler)

        # UI components
        self.chat_view = ChatView()
        self.debug_drawer = DebugDrawer(
            on_compact=self._manual_compact,
            on_clear=self._clear_history,
        )
        self.input_bar = InputBar(on_send=self._on_send)

        # State
        self._current_assistant_bubble: ft.Container | None = None
        self._current_md_text: str = ""
        self._log_path = self._init_log()

        self._build_ui()

    def _init_log(self) -> Path:
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        log_path = logs_dir / f"agent_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        log_path.write_text("", encoding="utf-8")
        return log_path

    def _build_ui(self):
        self.page.title = "AI Code Agent"
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.window.width = 1200
        self.page.window.height = 750
        self.page.window.min_width = 800
        self.page.window.min_height = 500
        self.page.padding = 0
        self.page.bgcolor = "#FFFFFF"

        # AppBar
        self.page.appbar = ft.AppBar(
            title=ft.Row([
                ft.Container(
                    content=ft.Text("A", size=10, color="white",
                                   weight=ft.FontWeight.W_700),
                    width=22, height=22, border_radius=5,
                    gradient=ft.LinearGradient(
                        begin=ft.alignment.top_left,
                        end=ft.alignment.bottom_right,
                        colors=["#6366F1", "#8B5CF6"],
                    ),
                    alignment=ft.alignment.center,
                ),
                ft.Text("AI Code Agent", size=14, weight=ft.FontWeight.W_600,
                        color="#1E1B3A"),
                ft.Container(
                    content=ft.Text(
                        f"{self.config.provider}  |  {self.config.model or 'default'}",
                        size=10, color="#94A3B8",
                    ),
                    bgcolor="#F1F3F6", border_radius=4,
                    padding=ft.padding.symmetric(horizontal=7, vertical=2),
                ),
            ], spacing=10),
            actions=[
                ft.TextButton(
                    text="配置", style=ft.ButtonStyle(
                        color="#64748B", text_style=ft.TextStyle(size=11),
                    ),
                    on_click=lambda e: show_config_dialog(
                        self.page, on_save=self._on_config_saved),
                ),
                ft.TextButton(
                    text="清除", style=ft.ButtonStyle(
                        color="#64748B", text_style=ft.TextStyle(size=11),
                    ),
                    on_click=lambda e: self._clear_history(),
                ),
                ft.TextButton(
                    text="调试", style=ft.ButtonStyle(
                        color="#94A3B8", text_style=ft.TextStyle(size=11),
                    ),
                    on_click=lambda e: self.debug_drawer._toggle(),
                ),
            ],
            bgcolor="#FAFBFC",
        )

        # Main layout
        main_row = ft.Row(
            [
                self.chat_view,
                self.debug_drawer,
            ],
            spacing=0,
        )

        self.page.add(main_row)
        self.page.add(self.input_bar)

        # Keyboard shortcut
        self.page.on_keyboard_event = self._on_keyboard

    # ── Agent event handlers (called from _FletEventHandler) ──

    def _on_thinking(self):
        self.chat_view.show_thinking()

    def _on_text_delta(self, token: str):
        self._current_md_text += token
        if self._current_assistant_bubble is None:
            avatar = ft.Container(
                content=ft.Text("AI", size=10, color="white",
                               weight=ft.FontWeight.W_600),
                width=28, height=28, border_radius=14,
                gradient=ft.LinearGradient(
                    begin=ft.alignment.top_left,
                    end=ft.alignment.bottom_right,
                    colors=["#6366F1", "#8B5CF6"],
                ),
                alignment=ft.alignment.center,
                shadow=ft.BoxShadow(
                    blur_radius=4,
                    color=ft.colors.with_opacity(0.25, "#6366F1"),
                    offset=ft.Offset(0, 1),
                ),
            )
            self._current_assistant_bubble = ft.Container(
                content=ft.Text(self._current_md_text, size=12, color="#1E1B3A",
                               selectable=True),
                bgcolor="#FAFBFC",
                border=ft.border.all(1, "#EEF0F4"),
                border_radius=ft.border_radius.only(
                    top_left=3, top_right=15, bottom_left=15, bottom_right=15,
                ),
                padding=ft.padding.symmetric(horizontal=15, vertical=10),
            )
            row = ft.Row(
                [avatar, self._current_assistant_bubble],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )
            self.chat_view.controls.append(row)
        else:
            self._current_assistant_bubble.content = ft.Markdown(
                self._current_md_text,
                selectable=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                code_theme="atom-one-light",
                code_style=ft.TextStyle(size=11, font_family="monospace"),
            )
        self._current_assistant_bubble.update()

    def _on_tool_use(self, name: str, input_dict: dict):
        preview = ", ".join(
            f"{k}={str(v)[:50]!r}" for k, v in input_dict.items()
        )
        self.chat_view.add_tool_label(name, preview)
        self.debug_drawer.add_event(
            "[Tool Call]", f"{name}: {preview}", "#6366F1",
        )

    def _on_tool_result(self, name: str, result: str, is_error: bool):
        color = "#EF4444" if is_error else "#10B981"
        preview = result[:300].replace("\n", " ")
        self.debug_drawer.add_event(
            "[Tool Result]",
            f"{name} ({len(result)} chars): {preview}",
            color,
        )

    def _on_response_done(self, raw: dict):
        if self._current_assistant_bubble is not None:
            self._current_assistant_bubble.content = ft.Markdown(
                self._current_md_text,
                selectable=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                code_theme="atom-one-light",
                code_style=ft.TextStyle(size=11, font_family="monospace"),
            )
            self._current_assistant_bubble.update()
        self._current_md_text = ""
        self._current_assistant_bubble = None

        # Token usage
        orig_usage = raw.get("usage", {})
        norm_usage = self._normalize_usage(orig_usage)
        self.debug_drawer.update_context_usage(norm_usage)

        # Log
        req = raw.get("_request", {})
        resp = {k: v for k, v in raw.items()
                if k not in ("_request", "_tool_use_blocks")}
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write("=" * 40 + " TURN " + "=" * 40 + "\n")
            f.write("── API Request ──\n")
            f.write(json.dumps(req, ensure_ascii=False, indent=2) + "\n\n")
            f.write("── API Response ──\n")
            f.write(json.dumps(resp, ensure_ascii=False, indent=2) + "\n")
            f.write("─" * 90 + "\n")

        # Event log
        msgs = req.get("messages", [])
        model = req.get("model", "?")
        prompt_tokens = norm_usage.get("prompt_tokens", "?")
        completion_tokens = norm_usage.get("completion_tokens", "?")
        self.debug_drawer.add_event(
            "[Response]", f"Model: {model}  |  Msgs: {len(msgs)}  |  "
            f"prompt={prompt_tokens}, completion={completion_tokens}",
            "#10B981",
        )

    def _on_done(self, final_text: str):
        self.chat_view.hide_thinking()
        self.input_bar.set_busy(False)

    def _on_error(self, message: str):
        self.debug_drawer.add_event("[Error]", message, "#EF4444")
        self.chat_view.hide_thinking()
        self.input_bar.set_busy(False)

    def _on_compact(self, pre_tokens: int, post_tokens: int, trigger: str):
        self.chat_view.add_tool_label(
            "Compact", f"~{pre_tokens} → ~{post_tokens} tokens ({trigger})",
        )
        self.debug_drawer.add_event(
            "[Compact]",
            f"Trigger: {trigger}\nTokens: ~{pre_tokens} → ~{post_tokens}",
            "#F59E0B",
        )
        self.debug_drawer.update_context_usage(
            {"prompt_tokens": post_tokens, "total_tokens": post_tokens},
        )

    # ── Normalization ──

    def _normalize_usage(self, usage: dict) -> dict:
        if not usage:
            return {}
        if "prompt_tokens" not in usage and "input_tokens" in usage:
            input_total = (
                (usage.get("input_tokens") or 0)
                + (usage.get("cache_creation_input_tokens") or 0)
                + (usage.get("cache_read_input_tokens") or 0)
            )
            output = usage.get("output_tokens") or 0
            cache_tokens = usage.get("cache_read_input_tokens") or 0
            return {
                "prompt_tokens": input_total,
                "completion_tokens": output,
                "total_tokens": input_total + output,
                "prompt_tokens_details": {"cached_tokens": cache_tokens},
            }
        if "total_tokens" not in usage:
            usage["total_tokens"] = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
        return usage

    # ── User actions ──

    def _on_send(self, text: str):
        if text.strip().lower() == "/compact":
            self._manual_compact()
            return

        self.chat_view.add_user_message(text)
        self.chat_view.show_thinking()
        self.input_bar.set_busy(True)

        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write("\n" + "*" * 60 + "\n")
            f.write(f"User: {text}\n")
            f.write("*" * 60 + "\n\n")

        self.page.run_task(self.controller.send_message, text)

    def _clear_history(self):
        self.controller.clear_history()
        self.chat_view.clear()
        self.debug_drawer.clear()

    def _on_config_saved(self, new_config: AgentConfig):
        self.config = new_config
        self.controller.reconfigure(new_config)
        self.chat_view.clear()
        self.debug_drawer.clear()
        self.debug_drawer.add_event(
            "System",
            f"Config updated: {new_config.provider} / {new_config.model}",
            "#6366F1",
        )

    def _manual_compact(self):
        self.page.run_task(self._do_compact)

    async def _do_compact(self):
        from compact.compact import compact_conversation
        from compact.grouping import estimate_tokens

        pre = estimate_tokens(self.controller.agent.messages)
        try:
            result = await compact_conversation(
                self.controller.agent.provider,
                self.controller.agent.messages,
                self.controller.agent.registry.get_schemas(),
                keep_recent_rounds=2,
                log_path=self._log_path,
            )
            if result.summary_messages:
                self.controller.agent.messages = (
                    result.summary_messages + result.messages_to_keep
                )
                self.controller.agent._last_actual_tokens = result.post_tokens
                self.controller.agent._compact_count += 1
                await self.handler.on_compact(
                    pre, result.post_tokens,
                    f"manual (#{self.controller.agent._compact_count})",
                )
            else:
                await self.handler.on_compact(pre, pre, "skipped (not enough messages)")
        except Exception as e:
            await self.handler.on_compact(pre, pre, f"failed: {e}")

    def _on_keyboard(self, e: ft.KeyboardEvent):
        if e.ctrl and e.key == "Enter":
            text = self.input_bar._text_field.value.strip()
            if text:
                self._on_send(text)
                self.input_bar._text_field.value = ""
                self.input_bar._text_field.update()


def launch_flet(config: AgentConfig):
    """Entry point for Flet desktop mode."""

    def main(page: ft.Page):
        FletApp(page, config)

    ft.app(target=main)
```

- [ ] **Step 2: 验证导入**

```bash
python -c "from flet_ui.app import launch_flet; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add flet_ui/app.py
git commit -m "feat: 新增 FletApp 主应用组装 + launch_flet 入口

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 9: main.py — 默认模式切换为 Flet

**Files:**
- Modify: `main.py:139-160`

- [ ] **Step 1: 修改 main.py 默认启动方式**

将 `main.py` 的第 153-157 行：

```python
if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Default: launch Qt GUI
        from qt_ui.main_window import launch
        launch(AgentConfig.from_yaml())
    else:
        asyncio.run(main())
```

替换为：

```python
if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Default: launch Flet GUI
        from flet_ui.app import launch_flet
        launch_flet(AgentConfig.from_yaml())
    else:
        asyncio.run(main())
```

- [ ] **Step 2: 验证 main.py 语法正确**

```bash
python -c "import ast; ast.parse(open('main.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: main.py 默认模式从 Qt 切换为 Flet

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 10: requirements.txt — 更新依赖

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: 替换 PySide6 为 flet**

将 `requirements.txt` 中的 `PySide6>=6.6` 替换为 `flet>=0.25`。

- [ ] **Step 2: 安装 flet**

```bash
pip install flet>=0.25
```

Expected: Flet 及其依赖安装成功。

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: 替换 PySide6 为 flet 依赖

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 11: 删除 qt_ui/ 目录

**Files:**
- Delete: `qt_ui/` (entire directory)

- [ ] **Step 1: 删除 qt_ui 目录**

```bash
rm -rf qt_ui/
git add -A qt_ui/
```

- [ ] **Step 2: 验证主入口不再引用 qt_ui**

```bash
grep -r "qt_ui" main.py || echo "No qt_ui references found"
```

Expected: `No qt_ui references found`

- [ ] **Step 3: Commit**

```bash
git commit -m "chore: 删除 qt_ui/ PySide6 界面

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 12: 端到端验证

- [ ] **Step 1: 验证终端交互模式不受影响**

```bash
python main.py -c "echo hello" 2>&1 | head -20
```

Expected: 正常运行，显示 working... 和结果（需要有效 API key）

- [ ] **Step 2: 验证 --help / -s 参数路由正常**

```bash
python -c "
import sys
sys.argv = ['main.py', '-s']
# Just verify imports work
from main import run_interactive
print('CLI mode imports OK')
"
```

Expected: `CLI mode imports OK`

- [ ] **Step 3: 验证所有模块导入正常**

```bash
python -c "
from controller import AgentController, EventHandler
from flet_ui.app import launch_flet, FletApp
from flet_ui.chat_view import ChatView
from flet_ui.input_bar import InputBar
from flet_ui.debug_drawer import DebugDrawer
from flet_ui.config_dialog import show_config_dialog
print('All imports OK')
"
```

Expected: `All imports OK`

- [ ] **Step 4: 验证 event 系统完整**

```bash
python -c "
from events import (ThinkingEvent, TextDeltaEvent, ToolUseEvent,
    ToolDoneEvent, ResponseDoneEvent, DoneEvent, ErrorEvent, CompactEvent)
print('All events:', CompactEvent.__name__)
"
```

Expected: `All events: CompactEvent`

- [ ] **Step 5: Commit**

```bash
git commit --allow-empty -m "chore: 端到端导入验证通过

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```
