# Qt Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 Textual TUI AI Agent 替换为 PySide6 Qt 桌面应用，支持流式逐字显示、可折叠 debug 面板、上下文窗口占用监控。

**Architecture:** 最小改动策略 — 核心 Agent/Provider/Tools 层不变，只新增 UI 层。Provider 加 `call_stream()` 实现流式，Agent 加 `run_stream()` async generator，Qt UI 通过 QThread worker 桥接。

**Tech Stack:** Python 3.11+, PySide6, asyncio, QThread

---

### Task 1: 创建 Event 类型定义

**Files:**
- Create: `events.py`

- [ ] **Step 1: 创建 events.py**

```python
"""Streaming event types shared by Agent, Providers, and UI."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ThinkingEvent:
    """Agent 开始思考（发起 LLM 请求前）"""


@dataclass
class TextDeltaEvent:
    """LLM 返回的一个文本 token"""
    token: str


@dataclass
class ToolUseEvent:
    """LLM 请求调用工具"""
    tool_name: str
    input: dict[str, Any]
    tool_use_id: str = ""


@dataclass
class ToolDoneEvent:
    """工具执行完毕"""
    tool_name: str
    result: str
    is_error: bool = False


@dataclass
class ResponseDoneEvent:
    """LLM 响应完成，含原始 API 返回数据"""
    raw: dict[str, Any]


@dataclass
class DoneEvent:
    """整个 run_stream() 完成"""
    final_text: str


@dataclass
class ErrorEvent:
    """发生错误"""
    message: str
```

- [ ] **Step 2: 验证文件无语法错误**

Run: `python -c "import events; print([e.__name__ for e in [events.ThinkingEvent, events.TextDeltaEvent, events.ToolUseEvent, events.ToolDoneEvent, events.ResponseDoneEvent, events.DoneEvent, events.ErrorEvent]])"`
Expected: `['ThinkingEvent', 'TextDeltaEvent', 'ToolUseEvent', 'ToolDoneEvent', 'ResponseDoneEvent', 'DoneEvent', 'ErrorEvent']`

- [ ] **Step 3: Commit**

```bash
git add events.py
git commit -m "feat: 添加流式 Event 类型定义"
```

---

### Task 2: Provider 层添加 call_stream()

**Files:**
- Modify: `providers/base.py` — 添加 `call_stream()` 抽象方法
- Modify: `providers/openai_compat.py` — 实现 `call_stream()`
- Modify: `providers/anthropic.py` — 实现 `call_stream()`

- [ ] **Step 1: 在 base.py 添加抽象方法**

在 `BaseProvider` 类的 `call()` 方法之后添加：

```python
@abstractmethod
async def call_stream(
    self,
    messages: list[Message],
    tools: list[dict],
    system: str,
):
    """
    Streaming call to LLM. Yields events: TextDeltaEvent, ToolUseEvent,
    ResponseDoneEvent, ErrorEvent.

    The generator yields events as they arrive from the LLM API.
    """
    ...
```

Note: 需要文件顶部添加 import：
```python
from typing import AsyncGenerator
```

- [ ] **Step 2: 在 openai_compat.py 实现 call_stream()**

在现有 `call()` 方法之后、`_assistant_to_openai` 之前添加：

```python
import asyncio
from events import TextDeltaEvent, ToolUseEvent, ResponseDoneEvent, ErrorEvent

async def call_stream(self, messages, tools, system):
    """OpenAI/GLM/DeepSeek 流式调用，逐 token yield."""
    from core_types import ToolUseBlock  # local to avoid circular

    # Build API messages (same as call())
    api_messages: list[dict] = [{"role": "system", "content": system}]
    for msg in messages:
        if msg.is_tool_result:
            api_messages.append({
                "role": "tool",
                "tool_call_id": msg.tool_use_id,
                "content": msg.content,
            })
        elif msg.role == "user":
            api_messages.append({"role": "user", "content": msg.content})
        elif msg.role == "assistant":
            api_messages.append(_assistant_to_openai(msg))

    openai_tools = None
    if tools:
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                },
            }
            for t in tools
        ]

    request_payload = {
        "model": self.model,
        "messages": api_messages,
        "tools": openai_tools,
        "max_tokens": self.max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    try:
        stream = await self.client.chat.completions.create(**request_payload)

        text_parts: list[str] = []
        tool_calls_buffer: dict[int, dict] = {}
        final_usage: dict = {}

        async for chunk in stream:
            if not chunk.choices:
                # 可能只有 usage 信息（末尾 chunk）
                if hasattr(chunk, "usage") and chunk.usage:
                    final_usage = chunk.usage.model_dump() if hasattr(chunk.usage, "model_dump") else {}
                continue

            delta = chunk.choices[0].delta

            if delta.content:
                text_parts.append(delta.content)
                yield TextDeltaEvent(token=delta.content)

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_buffer:
                        tool_calls_buffer[idx] = {
                            "id": tc.id or "",
                            "name": tc.function.name or "",
                            "arguments": "",
                        }
                    if tc.id:
                        tool_calls_buffer[idx]["id"] = tc.id
                    if tc.function.name:
                        tool_calls_buffer[idx]["name"] = tc.function.name
                    if tc.function.arguments:
                        tool_calls_buffer[idx]["arguments"] += tc.function.arguments

            # 收集 usage（如果在这个 chunk 里）
            if hasattr(chunk, "usage") and chunk.usage:
                final_usage = chunk.usage.model_dump() if hasattr(chunk.usage, "model_dump") else {}

        # Yield ResponseDone with raw info
        raw = {
            "_provider": self.provider_name,
            "_request": request_payload,
            "model": getattr(chunk, "model", self.model) if 'chunk' in dir() else self.model,
            "usage": final_usage,
        }

        # Parse tool calls from buffer → yield ToolUseEvent
        tool_use_blocks: list[ToolUseBlock] = []
        for tc_data in tool_calls_buffer.values():
            try:
                parsed = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
            except json.JSONDecodeError:
                parsed = {}
            block = ToolUseBlock(
                tool_use_id=tc_data["id"],
                tool_name=tc_data["name"],
                input=parsed,
            )
            tool_use_blocks.append(block)
            yield ToolUseEvent(
                tool_name=tc_data["name"],
                input=parsed,
                tool_use_id=tc_data["id"],
            )

        raw["_tool_use_blocks"] = [
            {"tool_name": t.tool_name, "tool_use_id": t.tool_use_id, "input": t.input}
            for t in tool_use_blocks
        ]
        yield ResponseDoneEvent(raw=raw)

    except Exception as e:
        yield ErrorEvent(message=f"Provider error: {e}")
```

- [ ] **Step 3: 在 anthropic.py 实现 call_stream()**

在现有 `call()` 方法之后、`_assistant_to_anthropic` 之前添加：

```python
async def call_stream(self, messages, tools, system):
    """Anthropic 流式调用，逐 event yield（重构自现有 call()）。"""
    from core_types import ToolUseBlock
    from events import TextDeltaEvent, ToolUseEvent, ResponseDoneEvent, ErrorEvent

    # Build API messages (same as call())
    api_messages: list[dict] = []
    for msg in messages:
        if msg.is_tool_result:
            api_messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": msg.tool_use_id,
                    "content": msg.content,
                }],
            })
        elif msg.role == "user":
            api_messages.append({"role": "user", "content": msg.content})
        elif msg.role == "assistant":
            api_messages.append(_assistant_to_anthropic(msg))

    api_tools = None
    if tools:
        api_tools = [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["parameters"],
            }
            for t in tools
        ]

    request_payload = {
        "model": self.model,
        "max_tokens": self.max_tokens,
        "system": system,
        "messages": api_messages,
        "tools": api_tools,
    }

    try:
        text_parts: list[str] = []
        tool_use_buffer: dict[int, dict] = {}
        tool_use_blocks: list[ToolUseBlock] = []

        async with self.client.beta.messages.stream(**request_payload) as stream:
            async for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        idx = event.index
                        tool_use_buffer[idx] = {
                            "id": block.id,
                            "name": block.name,
                            "input_json": "",
                        }

                elif event.type == "content_block_delta":
                    delta = event.delta
                    if hasattr(delta, "text") and delta.text:
                        text_parts.append(delta.text)
                        yield TextDeltaEvent(token=delta.text)
                    elif hasattr(delta, "partial_json") and delta.partial_json:
                        idx = event.index
                        if idx in tool_use_buffer:
                            tool_use_buffer[idx]["input_json"] += delta.partial_json

        # Parse tool use blocks
        for tc_data in tool_use_buffer.values():
            try:
                parsed = json.loads(tc_data["input_json"]) if tc_data["input_json"] else {}
            except json.JSONDecodeError:
                parsed = {}
            block = ToolUseBlock(
                tool_use_id=tc_data["id"],
                tool_name=tc_data["name"],
                input=parsed,
            )
            tool_use_blocks.append(block)
            yield ToolUseEvent(
                tool_name=tc_data["name"],
                input=parsed,
                tool_use_id=tc_data["id"],
            )

        final_msg = await stream.get_final_message()
        raw = final_msg.model_dump() if hasattr(final_msg, "model_dump") else {}
        raw["_provider"] = "anthropic"
        raw["_request"] = request_payload
        raw["_tool_use_blocks"] = [
            {"tool_name": t.tool_name, "tool_use_id": t.tool_use_id, "input": t.input}
            for t in tool_use_blocks
        ]
        yield ResponseDoneEvent(raw=raw)

    except Exception as e:
        yield ErrorEvent(message=f"Provider error: {e}")
```

- [ ] **Step 4: 验证导入和语法**

Run: `python -c "from providers.base import BaseProvider; from providers.openai_compat import OpenAICompatProvider; from providers.anthropic import AnthropicProvider; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add providers/base.py providers/openai_compat.py providers/anthropic.py
git commit -m "feat: Provider 层添加 call_stream() 流式方法"
```

---

### Task 3: Agent 层添加 run_stream()

**Files:**
- Modify: `agent.py` — 添加 `run_stream()` 方法

- [ ] **Step 1: 在 agent.py 添加 run_stream()**

在现有 `run()` 方法之后、`Agent` 类闭合之前添加：

```python
async def run_stream(self, user_message: str):
    """
    Streaming version of run(). Yields events instead of returning text.
    Provider must support call_stream().
    """
    from collections.abc import AsyncGenerator
    from events import (
        ThinkingEvent, TextDeltaEvent, ToolUseEvent, ToolDoneEvent,
        ResponseDoneEvent, DoneEvent, ErrorEvent,
    )

    self.messages.append(Message(role="user", content=user_message))

    turn_count = 0
    while turn_count < self.max_turns:
        turn_count += 1

        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]

        tools_schema = self.registry.get_schemas()
        system_prompt = build_system_prompt(
            self.registry.get_tool_names(),
            str(self.cwd),
        )

        yield ThinkingEvent()

        # Collect streaming events from provider
        text_parts: list[str] = []
        tool_use_blocks: list = []
        raw_response: dict = {}

        try:
            async for event in self.provider.call_stream(
                messages=self.messages,
                tools=tools_schema,
                system=system_prompt,
            ):
                if isinstance(event, TextDeltaEvent):
                    text_parts.append(event.token)
                    yield event
                elif isinstance(event, ToolUseEvent):
                    tool_use_blocks.append(ToolUseBlock(
                        tool_use_id=event.tool_use_id,
                        tool_name=event.tool_name,
                        input=event.input,
                    ))
                    yield event
                elif isinstance(event, ResponseDoneEvent):
                    raw_response = event.raw
                    yield event
                elif isinstance(event, ErrorEvent):
                    self.messages.append(Message(
                        role="assistant",
                        content=f"Error: {event.message}",
                    ))
                    yield event
                    yield DoneEvent(final_text=f"Error: {event.message}")
                    return
        except Exception as e:
            yield ErrorEvent(message=str(e))
            yield DoneEvent(final_text=f"Error: {e}")
            return

        assistant_text = "".join(text_parts)
        assistant_msg = Message(
            role="assistant",
            content=assistant_text,
            tool_use_blocks=[
                ToolUseBlock(
                    tool_use_id=t.tool_use_id if hasattr(t, 'tool_use_id') else "",
                    tool_name=t.tool_name if hasattr(t, 'tool_name') else t.get("tool_name", ""),
                    input=t.input if hasattr(t, 'input') else t.get("input", {}),
                )
                for t in (
                    tool_use_blocks
                    if tool_use_blocks
                    else raw_response.get("_tool_use_blocks", [])
                )
            ],
        )
        self.messages.append(assistant_msg)

        # Termination check
        final_blocks = assistant_msg.tool_use_blocks
        if not final_blocks:
            yield DoneEvent(final_text=assistant_text or "(no response)")
            return

        # Execute tools
        context = ToolContext(cwd=self.cwd, messages=list(self.messages))
        for block in final_blocks:
            tool = self.registry.get(block.tool_name)
            if tool is None:
                result_text = json.dumps({
                    "error": f"Unknown tool: {block.tool_name}"
                })
                is_error = True
            else:
                try:
                    result_text = await tool.call(block.input, context)
                    is_error = False
                except Exception as e:
                    result_text = f"Tool error: {e}"
                    is_error = True

            yield ToolDoneEvent(
                tool_name=block.tool_name,
                result=result_text,
                is_error=is_error,
            )

            self.messages.append(Message(
                role="user",
                content=result_text,
                tool_use_id=block.tool_use_id,
            ))

    yield DoneEvent(final_text="Agent: max turns reached without completing the task.")
```

需要在文件顶部添加 import：
```python
from events import (
    ThinkingEvent, TextDeltaEvent, ToolUseEvent, ToolDoneEvent,
    ResponseDoneEvent, DoneEvent, ErrorEvent,
)
```

Note: `run_stream()` 在方法内部 lazy import events 以避免循环依赖。`ToolUseBlock` 和 `Message` 已在 `core_types` 中导入。

- [ ] **Step 2: 验证语法和导入**

Run: `python -c "from agent import Agent; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add agent.py
git commit -m "feat: Agent 层添加 run_stream() 流式方法"
```

---

### Task 4: 创建 Qt AgentWorker（线程桥接）

**Files:**
- Create: `qt_ui/__init__.py`
- Create: `qt_ui/agent_worker.py`

- [ ] **Step 1: 创建 qt_ui/__init__.py**

```python
"""Qt UI package for AI Code Agent."""
```

- [ ] **Step 2: 创建 qt_ui/agent_worker.py**

```python
"""QThread worker that runs Agent.run_stream() and emits Qt signals."""

import asyncio

from PySide6.QtCore import QThread, Signal

from events import (
    ThinkingEvent, TextDeltaEvent, ToolUseEvent, ToolDoneEvent,
    ResponseDoneEvent, DoneEvent, ErrorEvent,
)


class AgentWorker(QThread):
    """Runs Agent.run_stream() in a worker thread, emits signals per event."""

    # Signals — all emitted from worker thread, auto-queued to main thread
    thinking = Signal()
    text_delta = Signal(str)
    tool_use = Signal(str, dict, str)  # name, input, tool_use_id
    tool_done = Signal(str, str, bool)  # name, result, is_error
    response_done = Signal(dict)  # raw response
    done = Signal(str)  # final_text
    error = Signal(str)  # error message

    def __init__(self, agent, user_message: str, parent=None):
        super().__init__(parent)
        self.agent = agent
        self.user_message = user_message
        self._cancel = False

    def cancel(self):
        """Signal the worker to stop after current LLM call completes."""
        self._cancel = True

    def run(self):
        """Entry point for QThread. Runs the asyncio event loop."""
        asyncio.run(self._run())

    async def _run(self):
        try:
            async for event in self.agent.run_stream(self.user_message):
                if self._cancel:
                    break

                if isinstance(event, ThinkingEvent):
                    self.thinking.emit()
                elif isinstance(event, TextDeltaEvent):
                    self.text_delta.emit(event.token)
                elif isinstance(event, ToolUseEvent):
                    self.tool_use.emit(event.tool_name, event.input, event.tool_use_id)
                elif isinstance(event, ToolDoneEvent):
                    self.tool_done.emit(event.tool_name, event.result, event.is_error)
                elif isinstance(event, ResponseDoneEvent):
                    self.response_done.emit(event.raw)
                elif isinstance(event, DoneEvent):
                    self.done.emit(event.final_text)
                elif isinstance(event, ErrorEvent):
                    self.error.emit(event.message)
                    self.done.emit(f"Error: {event.message}")
        except Exception as e:
            self.error.emit(str(e))
            self.done.emit(f"Error: {e}")
```

- [ ] **Step 4: 验证语法**

Run: `python -c "from qt_ui.agent_worker import AgentWorker; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add qt_ui/__init__.py qt_ui/agent_worker.py
git commit -m "feat: 创建 Qt AgentWorker 线程桥接"
```

---

### Task 5: 创建 InputBar 组件

**Files:**
- Create: `qt_ui/input_bar.py`

- [ ] **Step 1: 创建 qt_ui/input_bar.py**

```python
"""Bottom input bar: multi-line text input + send + stop buttons."""

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QTextEdit, QPushButton


class InputBar(QWidget):
    """Multi-line input area with send and stop buttons."""

    send_clicked = Signal(str)  # text content
    stop_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self._input = QTextEdit()
        self._input.setPlaceholderText("输入消息... (Ctrl+Enter 发送, Enter 换行)")
        self._input.setMaximumHeight(120)
        self._input.setMinimumHeight(40)
        self._input.setStyleSheet("""
            QTextEdit {
                background: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
            }
            QTextEdit:focus {
                border-color: #007acc;
            }
        """)

        self._send_btn = QPushButton("发送")
        self._send_btn.setFixedSize(70, 40)
        self._send_btn.setStyleSheet("""
            QPushButton {
                background: #0e639c;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #1177bb;
            }
            QPushButton:pressed {
                background: #0b5080;
            }
            QPushButton:disabled {
                background: #555;
                color: #999;
            }
        """)

        self._stop_btn = QPushButton("停止")
        self._stop_btn.setFixedSize(70, 40)
        self._stop_btn.setStyleSheet("""
            QPushButton {
                background: #8b0000;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #a00000;
            }
            QPushButton:pressed {
                background: #700000;
            }
            QPushButton:disabled {
                background: #555;
                color: #999;
            }
        """)
        self._stop_btn.setVisible(False)

        layout.addWidget(self._input)
        layout.addWidget(self._send_btn)
        layout.addWidget(self._stop_btn)

        # Connect signals
        self._send_btn.clicked.connect(self._on_send)
        self._stop_btn.clicked.connect(self._on_stop)

    def _on_send(self):
        text = self._input.toPlainText().strip()
        if text:
            self.send_clicked.emit(text)
            self._input.clear()

    def _on_stop(self):
        self.stop_clicked.emit()

    def set_streaming(self, streaming: bool):
        """Toggle between send mode and stop mode."""
        self._send_btn.setVisible(not streaming)
        self._stop_btn.setVisible(streaming)
        self._input.setEnabled(not streaming)

    def keyPressEvent(self, event):
        """Ctrl+Enter to send, plain Enter for newline."""
        if event.key() == Qt.Key_Return and event.modifiers() & Qt.ControlModifier:
            self._on_send()
        else:
            super().keyPressEvent(event)
```

- [ ] **Step 2: 验证语法**

Run: `python -c "from qt_ui.input_bar import InputBar; print('OK')"`
Expected: `OK` (不需要 QApplication 实例就能 import)

- [ ] **Step 3: Commit**

```bash
git add qt_ui/input_bar.py
git commit -m "feat: 创建 Qt InputBar 输入组件"
```

---

### Task 6: 创建 ChatPanel 组件

**Files:**
- Create: `qt_ui/chat_panel.py`

- [ ] **Step 1: 创建 qt_ui/chat_panel.py**

```python
"""Chat panel: scrollable message bubbles with streaming text support."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QLabel, QSizePolicy,
)


class ChatPanel(QWidget):
    """Scrollable chat area with message bubbles."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Title bar
        self._title = QLabel("AI Code Agent")
        self._title.setStyleSheet("""
            background: #2d2d2d;
            color: #ccc;
            padding: 8px 16px;
            font-weight: bold;
            font-size: 14px;
            border-bottom: 1px solid #444;
        """)
        layout.addWidget(self._title)

        # Scroll area for messages
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: #1e1e1e; }")

        self._msg_container = QWidget()
        self._msg_layout = QVBoxLayout(self._msg_container)
        self._msg_layout.setAlignment(Qt.AlignTop)
        self._msg_layout.setContentsMargins(12, 12, 12, 12)
        self._msg_layout.setSpacing(10)
        self._msg_layout.addStretch()

        self._scroll.setWidget(self._msg_container)
        layout.addWidget(self._scroll)

        # Track the current streaming bubble
        self._streaming_bubble: QLabel | None = None

    def set_title(self, text: str):
        self._title.setText(text)

    def add_user_message(self, text: str):
        """Add a user message bubble (right-aligned, blue)."""
        label = QLabel(text)
        label.setWordWrap(True)
        label.setMaximumWidth(int(self.width() * 0.7))
        label.setStyleSheet("""
            background: #0e639c;
            color: white;
            padding: 8px 14px;
            border-radius: 12px;
            font-size: 14px;
        """)
        label.setAlignment(Qt.AlignRight)
        # Insert before the stretch item
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, label,
                                       alignment=Qt.AlignRight)

    def add_assistant_message(self, text: str):
        """Add a completed assistant message bubble (left-aligned, dark)."""
        label = QLabel(text)
        label.setWordWrap(True)
        label.setMaximumWidth(int(self.width() * 0.8))
        label.setStyleSheet("""
            background: #3c3c3c;
            color: #d4d4d4;
            padding: 8px 14px;
            border-radius: 12px;
            font-size: 14px;
        """)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, label,
                                       alignment=Qt.AlignLeft)

    def add_tool_label(self, tool_name: str, input_preview: str):
        """Add a tool call label (purple, small)."""
        label = QLabel(f"🔧 {tool_name} — {input_preview}")
        label.setStyleSheet("""
            color: #c586c0;
            font-size: 12px;
            padding: 2px 8px;
        """)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, label,
                                       alignment=Qt.AlignLeft)

    def start_streaming(self):
        """Create a new assistant bubble for streaming text."""
        self._streaming_bubble = QLabel("")
        self._streaming_bubble.setWordWrap(True)
        self._streaming_bubble.setMaximumWidth(int(self.width() * 0.8))
        self._streaming_bubble.setStyleSheet("""
            background: #3c3c3c;
            color: #d4d4d4;
            padding: 8px 14px;
            border-radius: 12px;
            font-size: 14px;
        """)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1,
                                       self._streaming_bubble,
                                       alignment=Qt.AlignLeft)

    def append_token(self, token: str):
        """Append a token to the current streaming bubble."""
        if self._streaming_bubble:
            current = self._streaming_bubble.text()
            self._streaming_bubble.setText(current + token)
            # Auto-scroll to bottom
            self._scroll.verticalScrollBar().setValue(
                self._scroll.verticalScrollBar().maximum()
            )

    def finish_streaming(self):
        """Finalize the streaming bubble."""
        self._streaming_bubble = None

    def clear(self):
        """Remove all messages."""
        while self._msg_layout.count() > 1:  # keep the stretch
            item = self._msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
```

- [ ] **Step 2: 验证语法**

Run: `python -c "from qt_ui.chat_panel import ChatPanel; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add qt_ui/chat_panel.py
git commit -m "feat: 创建 Qt ChatPanel 聊天组件"
```

---

### Task 7: 创建 DebugPanel 组件（含上下文占用子面板）

**Files:**
- Create: `qt_ui/debug_panel.py`

- [ ] **Step 1: 创建 qt_ui/debug_panel.py**

```python
"""Collapsible debug panel with context usage sub-panel."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QTextBrowser, QLabel,
    QProgressBar, QSizePolicy,
)


class ContextUsageWidget(QWidget):
    """Shows token usage breakdown with progress bars."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(4)

        # Header
        self._header = QLabel("📊 上下文窗口占用  总计 — / —")
        self._header.setStyleSheet("""
            color: #007acc;
            font-weight: bold;
            font-size: 12px;
            padding: 4px 0;
        """)
        layout.addWidget(self._header)

        # Categories
        self._categories = {}
        for name, color in [
            ("System Prompt", "#569cd6"),
            ("对话消息", "#4ec9b0"),
            ("工具定义", "#c586c0"),
            ("缓存命中", "#ce9178"),
        ]:
            cat_widget = self._create_category(name, color)
            layout.addWidget(cat_widget)
            self._categories[name] = cat_widget

        # Total bar
        self._total_bar = QProgressBar()
        self._total_bar.setMaximum(1000)
        self._total_bar.setValue(0)
        self._total_bar.setFormat("总计 — / —")
        self._total_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #444;
                border-radius: 4px;
                background: #252525;
                height: 18px;
                text-align: center;
                color: white;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background: #4ec9b0;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self._total_bar)

        # Hidden by default until data arrives
        self.setVisible(False)

    def _create_category(self, name: str, color: str):
        """Create a label + mini progress bar row for a category."""
        row = QWidget()
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(2)

        label = QLabel(name)
        label.setStyleSheet(f"color: {color}; font-size: 11px;")
        row_layout.addWidget(label)

        bar = QProgressBar()
        bar.setMaximum(1000)
        bar.setValue(0)
        bar.setFormat("")
        bar.setFixedHeight(8)
        bar.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                border-radius: 4px;
                background: #333;
            }}
            QProgressBar::chunk {{
                background: {color};
                border-radius: 3px;
            }}
        """)
        row_layout.addWidget(bar)

        row._label = label
        row._bar = bar
        return row

    def update_usage(self, usage: dict, model_max: int = 128000):
        """Update from API response usage data."""
        prompt_tokens = usage.get("prompt_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)

        # Fixed values
        sys_tokens = 680  # approximate, set once at startup

        # Completion details
        completion_details = usage.get("completion_tokens_details", {}) or {}
        reasoning_tokens = completion_details.get("reasoning_tokens", 0) or 0

        # Prompt details
        prompt_details = usage.get("prompt_tokens_details", {}) or {}
        cached_tokens = prompt_details.get("cached_tokens", 0) or 0

        msg_tokens = prompt_tokens - sys_tokens - 48  # 48 = tools fixed
        tools_tokens = 48

        self._update_row("System Prompt", sys_tokens, model_max)
        self._update_row("对话消息", max(msg_tokens, 0), model_max)
        self._update_row("工具定义", tools_tokens, model_max)
        self._update_row("缓存命中", cached_tokens, model_max)

        self._total_bar.setMaximum(model_max)
        self._total_bar.setValue(total_tokens)
        self._total_bar.setFormat(f"总计 {total_tokens:,} / {model_max:,}")

        pct = total_tokens / model_max * 100 if model_max else 0
        self._header.setText(f"📊 上下文窗口占用  总计 {total_tokens:,} / {model_max:,} ({pct:.1f}%)")

        self.setVisible(True)

    def _update_row(self, name: str, tokens: int, max_tokens: int):
        row = self._categories.get(name)
        if not row:
            return
        row._label.setText(f"{name}  ({tokens:,})")
        row._bar.setMaximum(max_tokens)
        row._bar.setValue(tokens)


class DebugPanel(QDockWidget):
    """Dockable debug panel with log browser + context usage widget."""

    def __init__(self, parent=None):
        super().__init__("Debug Log", parent)
        self.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)
        self.setMinimumWidth(300)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Log browser (top portion - stretches)
        self._log = QTextBrowser()
        self._log.setStyleSheet("""
            QTextBrowser {
                background: #1a1a1a;
                color: #888;
                font-size: 12px;
                border: none;
                padding: 8px;
            }
        """)
        layout.addWidget(self._log, stretch=1)

        # Context usage (bottom portion - fixed)
        self._context = ContextUsageWidget()
        layout.addWidget(self._context)

        self.setWidget(container)

    def add_entry(self, title: str, content: str, color: str = "#888"):
        """Add a formatted log entry."""
        self._log.append(
            f'<p><b style="color:{color}">{title}</b></p>'
            f'<pre style="font-size:11px;color:#999;margin:4px 0">{content}</pre>'
            f'<hr style="border-color:#333">'
        )

    def update_context_usage(self, usage: dict, model_max: int = 128000):
        """Update the context usage sub-panel."""
        self._context.update_usage(usage, model_max)

    def clear(self):
        self._log.clear()
```

- [ ] **Step 2: 验证语法**

Run: `python -c "from qt_ui.debug_panel import DebugPanel, ContextUsageWidget; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add qt_ui/debug_panel.py
git commit -m "feat: 创建 Qt DebugPanel 含上下文占用子面板"
```

---

### Task 8: 创建 MainWindow 和 launch 入口

**Files:**
- Create: `qt_ui/main_window.py`

- [ ] **Step 1: 创建 qt_ui/main_window.py**

```python
"""Main Qt window: assembles ChatPanel, DebugPanel, InputBar, AgentWorker."""

import json
import sys
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QStatusBar, QApplication,
)

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
from qt_ui.chat_panel import ChatPanel
from qt_ui.debug_panel import DebugPanel
from qt_ui.input_bar import InputBar
from qt_ui.agent_worker import AgentWorker


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register_all([
        BashTool(), FileReadTool(), FileEditTool(),
        FileWriteTool(), GlobTool(), GrepTool(),
    ])
    return registry


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


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, config: AgentConfig):
        super().__init__()
        self.setWindowTitle("AI Code Agent")
        self.resize(1200, 750)
        self.setMinimumSize(800, 500)

        # Dark theme
        self.setStyleSheet("""
            QMainWindow { background: #1e1e1e; }
            QMenuBar {
                background: #2d2d2d;
                color: #ccc;
                border-bottom: 1px solid #444;
            }
            QMenuBar::item:selected {
                background: #094771;
            }
            QStatusBar {
                background: #007acc;
                color: white;
                font-size: 12px;
            }
        """)

        # Menubar
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        file_menu.addAction("Clear History", self._clear_history)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        # Central area: chat panel fills available space
        self.chat = ChatPanel()
        self.chat.set_title(
            f"AI Code Agent  |  {config.provider}  |  {config.model or 'default'}"
        )

        # Debug panel: dockable right sidebar
        self.debug = DebugPanel()
        self.debug.setVisible(True)
        self.addDockWidget(Qt.RightDockWidgetArea, self.debug)

        # Input bar: fixed at bottom
        self.input_bar = InputBar()
        self.input_bar.send_clicked.connect(self._on_send)
        self.input_bar.stop_clicked.connect(self._on_stop)

        # Assemble: chat (stretch) + input (fixed) in a vertical layout
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.chat)
        central_layout.addWidget(self.input_bar)
        self.setCentralWidget(central)

        # Status bar
        self._status = QStatusBar()
        self._status.showMessage(
            f"Provider: {config.provider}  |  Model: {config.model or 'default'}  |  "
            f"CWD: {config.cwd or Path.cwd()}"
        )
        self.setStatusBar(self._status)

        # Agent + worker
        registry = build_registry()
        provider = build_provider(config)
        self.agent = Agent(
            provider=provider, registry=registry,
            cwd=config.cwd,
            max_turns=config.max_turns,
            max_messages=config.max_messages,
        )
        self._worker: AgentWorker | None = None

        # Log file (same as old TUI)
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        self._log_path = logs_dir / f"agent_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self._log_path.write_text("", encoding="utf-8")

    def _on_send(self, text: str):
        """User clicked send."""
        self.chat.add_user_message(text)

        # Log conversation separator
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write("\n" + "*" * 60 + "\n")
            f.write(f"User: {text}\n")
            f.write("*" * 60 + "\n\n")

        # Start worker
        self._worker = AgentWorker(self.agent, text)
        self._worker.thinking.connect(self._on_thinking)
        self._worker.text_delta.connect(self._on_text_delta)
        self._worker.tool_use.connect(self._on_tool_use)
        self._worker.tool_done.connect(self._on_tool_done)
        self._worker.response_done.connect(self._on_response_done)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_worker_finished)

        self.input_bar.set_streaming(True)
        self._worker.start()

    def _on_stop(self):
        """User clicked stop."""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()

    # ── Agent callbacks ──────────────────────────────────────

    def _on_thinking(self):
        self.chat.start_streaming()

    def _on_text_delta(self, token: str):
        self.chat.append_token(token)

    def _on_tool_use(self, name: str, input: dict, tool_use_id: str):
        preview = ", ".join(
            f"{k}={str(v)[:50]!r}" for k, v in input.items()
        )
        self.chat.add_tool_label(name, preview)

    def _on_tool_done(self, name: str, result: str, is_error: bool):
        color = "#f44747" if is_error else "#4ec9b0"
        preview = result[:500].replace("\n", " ")
        msg = f"Tool: {name}\nResult ({len(result)} chars): {preview}"
        self.debug.add_entry("📥 Tool Result", msg, color)

    def _on_response_done(self, raw: dict):
        # Log request + response
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write("=" * 40 + " TURN " + "=" * 40 + "\n")
            f.write("── API Request ──\n")
            f.write(json.dumps(raw.pop("_request", {}), ensure_ascii=False, indent=2) + "\n\n")
            f.write("── API Response ──\n")
            f.write(json.dumps(raw, ensure_ascii=False, indent=2) + "\n")
            f.write("─" * 90 + "\n")

        # Show response in debug
        tool_blocks = raw.get("_tool_use_blocks", [])
        if tool_blocks:
            names = [t["tool_name"] for t in tool_blocks]
            self.debug.add_entry("📥 Response", f"Tool calls: {', '.join(names)}", "#4ec9b0")
        else:
            self.debug.add_entry("📥 Response", "Text response", "#4ec9b0")

        # Update context usage
        usage = raw.get("usage", {})
        model_max = 128000  # could be config-driven
        self.debug.update_context_usage(usage, model_max)

    def _on_done(self, final_text: str):
        self.chat.finish_streaming()

    def _on_error(self, message: str):
        self.debug.add_entry("❌ Error", message, "#f44747")

    def _on_worker_finished(self):
        self.input_bar.set_streaming(False)
        self._worker = None

    def _clear_history(self):
        self.agent.messages.clear()
        self.chat.clear()
        self.debug.clear()


def launch(config: AgentConfig):
    """Entry point for Qt mode. Creates QApplication and MainWindow."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Dark palette
    from PySide6.QtGui import QPalette, QColor
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.WindowText, QColor(212, 212, 212))
    palette.setColor(QPalette.Base, QColor(30, 30, 30))
    palette.setColor(QPalette.Text, QColor(212, 212, 212))
    palette.setColor(QPalette.Button, QColor(45, 45, 45))
    palette.setColor(QPalette.ButtonText, QColor(212, 212, 212))
    palette.setColor(QPalette.Highlight, QColor(0, 122, 204))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    window = MainWindow(config)
    window.show()
    app.exec()
```

- [ ] **Step 2: 验证语法**

Run: `python -c "from qt_ui.main_window import MainWindow, launch; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add qt_ui/main_window.py
git commit -m "feat: 创建 Qt MainWindow 主窗口和 launch 入口"
```

---

### Task 9: 更新 main.py 入口 + requirements.txt

**Files:**
- Modify: `main.py` — Qt 默认入口
- Modify: `requirements.txt` — 加 PySide6

- [ ] **Step 1: 更新 main.py**

将 `main.py` 的 `if __name__ == "__main__"` 部分改为：

```python
if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Default: launch Qt GUI
        from qt_ui.main_window import launch
        launch(AgentConfig.from_yaml())
    else:
        asyncio.run(main())
```

保持 `main()` 函数中第 148-151 行不变（TUI 分支删掉，因为 tui.py 不再使用）。修改后的 `main()`：

```python
async def main():
    config = AgentConfig.from_yaml()

    if len(sys.argv) >= 3 and sys.argv[1] == "-c":
        await run_one_shot(config, " ".join(sys.argv[2:]))
    elif len(sys.argv) >= 2 and sys.argv[1] == "-s":
        await run_interactive(config)
    elif len(sys.argv) >= 2 and sys.argv[1] not in ("-s", "-c"):
        await run_one_shot(config, " ".join(sys.argv[1:]))
    else:
        # Qt mode — handled in __name__ == "__main__"
        pass
```

- [ ] **Step 2: 更新 requirements.txt**

```
anthropic>=0.40.0
openai>=1.50.0
pydantic>=2.0.0
pyyaml>=6.0
PySide6>=6.6
```

去掉 `textual>=1.0.0`。

- [ ] **Step 3: 验证 main.py 语法**

Run: `python -c "import ast; ast.parse(open('main.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 4: 端到端启动测试**

Run: `python main.py`（需要显示器环境 — 如果有 GUI 环境，应该看到窗口弹出；headless 环境会报 `qt.qpa.xcb: could not connect to display`，这是正常的）

- [ ] **Step 5: Commit**

```bash
git add main.py requirements.txt
git commit -m "feat: 更新 main.py 入口为 Qt 默认，加 PySide6 依赖"
```

---

### Task 10: 清理和最终验证

**Files:**
- Delete: `tui.py`

- [ ] **Step 1: 删除 tui.py**

```bash
git rm tui.py
```

- [ ] **Step 2: 全量导入检查**

Run: `python -c "
from agent import Agent
from events import *
from providers.base import BaseProvider
from providers.anthropic import AnthropicProvider
from providers.openai_compat import OpenAICompatProvider
from qt_ui.main_window import MainWindow, launch
from qt_ui.chat_panel import ChatPanel
from qt_ui.debug_panel import DebugPanel, ContextUsageWidget
from qt_ui.input_bar import InputBar
from qt_ui.agent_worker import AgentWorker
print('All imports OK')
"`
Expected: `All imports OK`

- [ ] **Step 3: 运行 CLI 模式确保不破坏**

Run: `python main.py -c "hello"`
Expected: Agent 正常调用 LLM 并返回结果（CLI 模式不受影响）

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: 删除 tui.py，完成 Qt 迁移"
```
