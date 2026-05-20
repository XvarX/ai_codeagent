# Qt Migration Design

## Context

将现有 Textual TUI 的 AI 编码 Agent 改为 PySide6 Qt 桌面应用。核心三层（Agent / Provider / Tools）保持不动，只换 UI 层。

## Scope

- 在原项目上直接改，`tui.py` → `qt_ui/` 目录
- 现有 CLI 模式（`-s` 交互 / `-c` 一次性）保留
- Qt 版新增：流式逐字显示、可折叠 debug 侧栏、上下文窗口占用面板
- Provider 层加 `call_stream()` 方法实现流式
- Agent 层加 `run_stream()` async generator
- `main.py` 入口适配：无参数时启动 Qt 窗口

## 文件变更

| 文件 | 动作 | 说明 |
|---|---|---|
| `requirements.txt` | 改 | 加 `PySide6>=6.6`，去 `textual` |
| `providers/base.py` | 改 | `call()` 返回值改为 3-tuple（已在之前改好），新增 `call_stream()` 抽象方法 |
| `providers/openai_compat.py` | 改 | 加 `call_stream()`，用 `stream=True` SSE 流式，逐 token yield |
| `providers/anthropic.py` | 改 | 重构现有流式机制为 `call_stream()`，逐 event yield |
| `agent.py` | 改 | 加 `run_stream()` async generator，统一返回 7 种 Event |
| `tui.py` | 删 | |
| `qt_ui/__init__.py` | 新 | |
| `qt_ui/main_window.py` | 新 | QMainWindow，组装各组件 + `launch()` 入口 |
| `qt_ui/chat_panel.py` | 新 | 聊天区：消息气泡列表 + 流式文本追加 |
| `qt_ui/debug_panel.py` | 新 | 可折叠 debug 侧栏（QDockWidget）+ 上下文占用子面板 |
| `qt_ui/input_bar.py` | 新 | 底部输入栏：QTextEdit + 发送 + 停止按钮 |
| `qt_ui/agent_worker.py` | 新 | QThread worker，桥接 `run_stream()` 到 Qt 信号槽 |
| `main.py` | 改 | 入口：无参数 → Qt；`-s`/`-c` 保留 |
| `config.yaml` | 不变 | |
| `prompts.py` | 不变 | |
| `events.py` | 新 | 7 种流式 Event dataclass 定义 |
| `core_types.py` | 不变 | |
| `tools/` 全部 | 不变 | |

## UI 架构

### Widget 树

```
QMainWindow
├── QMenuBar (File, Settings, Help)
├── QSplitter (horizontal)
│   ├── ChatPanel (QWidget)
│   │   ├── QLabel (标题: model info)
│   │   ├── QScrollArea
│   │   │   └── 动态消息气泡
│   │   └── InputBar (QWidget)
│   │       ├── QTextEdit (多行输入，Ctrl+Enter 发送)
│   │       ├── QPushButton "发送"
│   │       └── QPushButton "停止"
│   └── DebugPanel (QDockWidget) ← 可折叠/拖拽/关闭
│       ├── QTextBrowser (debug log)
│       └── ContextUsageWidget (上下文占用子面板)
└── QStatusBar (provider, model, cwd)
```

### 关键交互

- **输入**：Ctrl+Enter 发送，Enter 换行
- **Debug 面板**：QDockWidget 右侧停靠，可折叠 ✕、拖拽、调宽度
- **流式显示**：token 逐个追加到当前消息气泡末尾，带光标闪烁
- **停止按钮**：设 cancel 标志位，worker 线程检测后退出 Agent 循环
- **复制**：Qt 原生支持 Ctrl+C 选中文字

### 上下文占用子面板

位于 Debug 面板底部，每轮 API 返回后更新：

| 分类 | 数据源 | 精度 |
|---|---|---|
| System Prompt | 启动时计算一次，固定值 | 准确 |
| 对话消息 | 上轮 `usage.prompt_tokens` - 固定项 | 上轮准确 |
| 工具定义 | 6 个工具 schema，固定 | 准确 |
| 缓存命中 | `usage.prompt_tokens_details.cached_tokens`（GLM）或 Anthropic cache | 准确 |
| 本轮增量 | 新消息按 `字符数/4` 估算（中文 `/2`） | 估算 |

每轮两阶段：
1. 发请求前：显示上轮准确值 + 本轮增量估算
2. 收到响应后：用 `usage` 中的准确值替换

显示形式：分类名 + token 数 + 迷你进度条（占比），顶部显示总量/模型上限。

## 流式数据流

### Event 类型定义（`events.py` 新文件）

7 种 Event 用 dataclass 定义，存入新文件 `events.py`（放在项目根目录，Agent/Provider/UI 三方共用）：

```python
@dataclass
class ThinkingEvent: ...
@dataclass
class TextDeltaEvent:   token: str
@dataclass
class ToolUseEvent:     tool_name: str, input: dict
@dataclass
class ToolDoneEvent:    tool_name: str, result: str, is_error: bool
@dataclass
class ResponseDoneEvent: raw: dict  # 含 usage, model, finish_reason 等
@dataclass
class DoneEvent:        final_text: str
@dataclass
class ErrorEvent:       message: str
```

### Provider 层

Agent 的 `run_stream()` 统一 yield 以下 Event：

| Event | 携带数据 | UI 动作 |
|---|---|---|
| `thinking` | — | 显示加载指示器 |
| `text_delta` | token: str | 追加到当前消息气泡 |
| `tool_use` | tool_name, input | 显示 🔧 工具调用标签 |
| `tool_done` | tool_name, result, is_error | debug 面板显示结果 |
| `response_done` | raw_response dict | 更新 token 用量、debug 日志 |
| `done` | final_text | 结束流式，最终化消息 |
| `error` | error_message | 显示错误提示 |

### Provider 层

两个 provider 都新增 `call_stream()` 方法，与现有 `call()` 并存：

- **OpenAICompatProvider**：`stream=True` SSE 流式，逐 chunk 解析 `choices[0].delta`
- **AnthropicProvider**：复用现有 `beta.messages.stream`，重构为逐 event yield（`content_block_start` / `content_block_delta`）

两个 provider 返回相同的 Event 类型，Agent 不感知 provider 差异。

### Agent 层

```python
async def run_stream(self, user_message: str) -> AsyncGenerator[Event, None]:
    messages.append(Message(role="user", content=user_message))

    while turn < max_turns:
        yield ThinkingEvent()
        async for event in provider.call_stream(...):
            if isinstance(event, TextDelta):
                yield event  # 逐 token 透传
            elif isinstance(event, ResponseDone):
                yield event  # 含 raw_response
        if not tool_use_blocks:
            yield DoneEvent(final_text)
            break
        for block in tool_use_blocks:
            yield ToolUseEvent(block.name, block.input)
            result = await tool.call(...)
            yield ToolDoneEvent(block.name, result, is_error)
            messages.append(tool_result_msg)
```

`run()` 保留不变，供 CLI 模式使用。

### Qt 线程模型

```
主线程 (Qt UI): MainWindow, ChatPanel, DebugPanel
     ▲  signal/slot 连接
Worker 线程 (QThread): AgentWorker
     async for event in agent.run_stream():
         text_delta_signal.emit(token)
         tool_use_signal.emit(name, input)
         response_done_signal.emit(raw)
         ...
```

Agent 的 while-true 循环在 worker 线程跑，通过 `Signal` 把事件推到主线程更新 UI。停止按钮设 cancel 标志，worker 检测后退出循环。

## main.py 入口

```python
# python main.py        → Qt 窗口
# python main.py -s     → 终端交互模式（不变）
# python main.py -c "x" → 一次性模式（不变）
# python main.py "x"    → 简写一次性模式（不变）

if __name__ == "__main__":
    if len(sys.argv) == 1:
        from qt_ui.main_window import launch
        launch(AgentConfig.from_yaml())
    else:
        asyncio.run(main())
```

`qt_ui/main_window.py` 的 `launch(config)` 负责：创建 QApplication、实例化 MainWindow、启动 Qt 事件循环。

## 技术选型

- **GUI 框架**：PySide6
- **流式**：Provider 加 `call_stream()`，Agent 加 `run_stream()` async generator
- **线程**：QThread + Qt Signal（主线程 UI / worker 线程 Agent）

## 注意事项

- `config.yaml` 中的 API key 敏感信息，Qt UI 不做脱敏显示
- `ctrl+c` 问题在 Qt 中不存在（GUI 原生支持 Ctrl+C 复制）
- Debug 面板右侧停靠为默认，可自由拖拽
- 原 CLI 模式（`-s`/`-c`）零改动
