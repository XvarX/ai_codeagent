# Flet 迁移 + 前后端分离 设计文档

**日期**: 2026-05-22
**版本**: 1.0

---

## 1. 背景与目标

当前 AI Code Agent 的 UI 层基于 PySide6 (Qt)，代码在 `qt_ui/` 目录下。UI 和 Agent 后端存在强耦合——`main_window.py` 直接 import Agent/Provider/ToolRegistry，AgentWorker 通过 QThread + Qt Signal 桥接回调。

### 目标

1. **前后端分离**：创建 `AgentController` 封装 Agent 生命周期，UI 层不直接依赖 Agent/Provider
2. **Flet 替换 Qt**：用 Flet 重写桌面 UI，删除 `qt_ui/`
3. **终端模式不变**：`-s` 交互终端和 `-c` 命令行保持原样

### 不变的部分

`agent.py`、`events.py`、`core_types.py`、`prompts.py`、`config.py`、`providers/`、`tools/`、`compact/` 全部保留不动。

---

## 2. 架构设计

```
main.py
├── 默认模式（无参数）    → launch_flet(config)
├── -s 终端交互           → run_interactive(config)    [不变]
├── -c "msg" / "msg"      → run_one_shot(config, msg)  [不变]
│
└── 共享层
    └── AgentController (controller.py)
        ├── 封装 Agent 创建 + 生命周期
        ├── 内部使用 agent.run_stream()
        └── 通过 event_handler 回调通知 UI
```

### AgentController 接口

```python
class AgentController:
    def __init__(self, config, event_handler)
    async def send_message(text: str) -> None
    async def cancel() -> None
    def clear_history() -> None
    def reconfigure(new_config) -> None
    def estimate_usage() -> dict

# EventHandler (所有方法都是 async)
class EventHandler:
    async def on_thinking(self): ...
    async def on_text_delta(self, token: str): ...
    async def on_tool_use(self, name: str, input: dict): ...
    async def on_tool_result(self, name: str, result: str, is_error: bool): ...
    async def on_response_done(self, raw: dict): ...
    async def on_done(self, final_text: str): ...
    async def on_error(self, message: str): ...
    async def on_compact(self, pre: int, post: int, trigger: str): ...
```

### 数据流

```
用户输入 → InputBar.on_submit(text)
  → FletApp._on_send(text)
    → page 即时添加 user_bubble
    → asyncio.create_task(controller.send_message(text))
      → agent.run_stream(user_message)
        → ThinkingEvent     → thinking 动画
        → TextDeltaEvent    → assistant_bubble 尾部追加
        → ToolUseEvent      → tool 标签
        → ToolDoneEvent     → debug drawer 日志
        → ResponseDoneEvent → 上下文用量更新
        → DoneEvent         → 移除 thinking 动画
        → ErrorEvent        → 错误提示
```

---

## 3. 文件变更总览

| 操作 | 路径 | 说明 |
|------|------|------|
| 新增 | `controller.py` | AgentController + EventHandler 基类 |
| 新增 | `flet_ui/__init__.py` | 包初始化 |
| 新增 | `flet_ui/app.py` | Flet Page 组装、事件绑定、主入口 |
| 新增 | `flet_ui/chat_view.py` | 聊天气泡列表、Markdown 渲染 |
| 新增 | `flet_ui/input_bar.py` | 底部输入框 + 发送按钮 |
| 新增 | `flet_ui/debug_drawer.py` | 可折叠调试面板 |
| 新增 | `flet_ui/config_dialog.py` | Provider 配置对话框 |
| 修改 | `main.py` | 默认模式从 Qt → Flet 启动 |
| 修改 | `requirements.txt` | PySide6 → flet |
| 删除 | `qt_ui/` | 整个目录 |

---

## 4. Flet UI 设计

### 布局：方案 B — 简化为聊天 + 可折叠调试抽屉

```
┌──────────────────────────────────────┐
│ 顶栏：AppBar                         │
│ AI Code Agent │ glm-5.1  [配置][清除][调试] │
├──────────────────────────┬───────────┤
│                          │ 调试面板   │
│  聊天区 (ListView)       │ (可折叠)   │
│                          │           │
│  ┌──────────────┐       │ 上下文用量 │
│  │  用户气泡     │       │ ████░░ 38% │
│  └──────────────┘       │           │
│     ┌──────────────┐    │ 事件日志   │
│     │ AI 气泡       │    │ [Request]  │
│     │ + Markdown   │    │ [Response] │
│     │ + 代码高亮   │    │ [Tool]     │
│     └──────────────┘    │           │
│  Bash python sort.py     │ 快捷操作   │
│  思考中...               │ [Compact]  │
│                          │ [Clear]    │
├──────────────────────────┴───────────┤
│ 输入底栏：[输入消息...]         [↑] │
└──────────────────────────────────────┘
```

### 配色：浅白 Indigo 主题

| 用途 | 色值 | 说明 |
|------|------|------|
| 页面背景 | `#FFFFFF` | 纯白 |
| 表面/顶栏/底栏 | `#FAFBFC` | 微灰 |
| 用户气泡 | `#F1F3F6` | 浅灰 |
| AI 气泡 | `#FAFBFC` + `#EEF0F4` 边框 | 微蓝灰 |
| 强调色 | `#6366F1` | Indigo |
| 主文字 | `#1E1B3A` | 深靛灰 |
| 辅助文字 | `#64748B` | 灰蓝 |
| 边框 | `#E2E6EC` / `#EEF0F4` | 浅灰边框 |
| 成功色 | `#10B981` | 绿色 |

### 风格：Minimalism & Swiss Style

- 干净、宽敞、功能性优先，无多余装饰
- 网格化布局，充足留白
- WCAG AAA 高对比度
- 圆角：气泡 14-15px，卡片 10px，按钮 9px
- 动效：微交互 200-250ms，抽屉滑动 200ms ease-out

### Flet 控件映射

| 功能 | Flet 控件 |
|------|----------|
| 聊天列表 | `ft.ListView` (expand=True) |
| 用户气泡 | `ft.Container` 右对齐 |
| AI 气泡 + Markdown | `ft.Container` + `ft.Markdown` |
| 工具调用标签 | `ft.Container` + `ft.Text` |
| Thinking 动画 | `ft.ProgressRing` 或三点脉动 |
| 输入框 | `ft.TextField` (multiline, shift_enter=True) |
| 发送按钮 | `ft.IconButton` (ft.icons.SEND) |
| 调试抽屉 | `ft.AnimatedContainer` 控制宽度 |
| 上下文进度条 | `ft.ProgressBar` |
| 事件日志 | `ft.ListView` 或 `ft.Column` |
| 配置对话框 | `ft.AlertDialog` |

---

## 5. Flet 组件详细设计

### 5.1 chat_view.py — ChatView

- 继承 `ft.ListView`，auto_scroll=True
- 方法：
  - `add_user_message(text)` — 蓝色闪光点 + 右对齐气泡
  - `add_assistant_message(text)` — AI 渐变头像 + 左对齐气泡，内含 `ft.Markdown`
  - `add_tool_label(name, preview)` — 工具调用标签
  - `add_thinking_indicator()` / `remove_thinking_indicator()` — 思考中动画
  - `clear()`

### 5.2 input_bar.py — InputBar

- `ft.Row` 包含 `ft.TextField` + `ft.IconButton`
- TextField: multiline=True, shift_enter=True, 自动增高（max_lines=6）
- IconButton: ft.icons.SEND, bgcolor accent
- `send_clicked` 回调属性
- `set_busy(bool)` 控制发送按钮禁用态

### 5.3 debug_drawer.py — DebugDrawer

- `ft.AnimatedContainer` 控制宽度：36px（折叠）↔ 260px（展开）
- 折叠时：竖向文字"调试" + 脉冲指示灯（有新事件时）
- 展开后：
  - 标题行 "调试面板" + 关闭按钮
  - ContextUsageBar：`ft.ProgressBar` + `ft.Text` 百分比
  - EventLog：`ft.ListView` 滚动日志，最多 50 条
  - 快捷按钮行：[Compact] [Clear History]
- 方法：
  - `add_event(prefix, message, color)`
  - `update_context_usage(usage_dict)`
  - `clear()`

### 5.4 config_dialog.py — ConfigDialog

- `ft.AlertDialog` 弹窗
- Provider 下拉选择（anthropic/openai/glm/deepseek）
- API Key 输入 + Model 输入 + Base URL 输入
- 保存到 `config.yaml`，调用 `controller.reconfigure()`

### 5.5 app.py — FletApp（组装入口）

- `main(page: ft.Page)` 函数
- Page 设置：
  - `page.title = "AI Code Agent"`
  - `page.theme_mode = ft.ThemeMode.LIGHT`
  - `page.window.width = 1200`, `page.window.height = 750`
  - `page.padding = 0`
  - `page.bgcolor = "#FFFFFF"`
- 组装：AppBar → Row(ChatView + DebugDrawer) → InputBar
- 事件绑定：`page.on_keyboard_event` 处理 Ctrl+Enter
- 创建 AgentController 实例，传入 EventHandler 实现

---

## 6. 关键实现细节

### 6.1 AgentController 内部

- 构造函数中 `build_registry()` + `build_provider(config)` + `Agent(...)`
- `send_message()` 内部 `async for event in self.agent.run_stream(text):` 消费事件
- `cancel()` 设置 `asyncio.Event`，在 `run_stream` 的工具执行循环前检查
- 不复用 `run_stream` 的紧凑逻辑（当前版本尚未集成 compact pipeline），需要在其内部添加 compact 调用

### 6.2 run_stream 的 compact 集成

当前 `run_stream()` 缺少 `run()` 方法中的压缩管线（history snip → micro compact → auto compact）。AgentController 需要在 `run_stream` 循环中插入紧凑逻辑，或者将紧凑管线提取为 Agent 的独立方法供 `run_stream` 复用。

方案：在 `run_stream()` 的 while 循环顶部添加与 `run()` 相同的压缩调用：
```python
# run_stream 循环顶部添加
if len(self.messages) > self.max_messages:
    self.messages = self.messages[-self.max_messages:]
if turn_count > 1:
    from compact.microCompact import micro_compact
    micro_compact(self.messages)
from compact.autoCompact import should_auto_compact
if should_auto_compact(...):
    await compact_conversation(...)
```

### 6.3 配置文件修改

- `config.py` 保持不变
- `config.yaml` 格式保持不变
- Flet UI 的 ConfigDialog 直接读写 `config.yaml`

### 6.4 构建/打包

- `requirements.txt` 中 `PySide6>=6.6` 替换为 `flet>=0.25`
- `build_exe.bat` 和 `AI_CodeAgent.spec` 更新依赖路径
- 新增的 `controller.py` 和 `flet_ui/` 需要包含在打包中

---

## 7. 验证计划

### 7.1 功能验证

1. `python main.py` 启动 Flet 桌面界面
2. 输入消息，验证 AI 回复正常显示（Markdown 渲染、代码高亮）
3. 验证工具调用标签展示正确
4. 验证调试抽屉展开/折叠、事件日志、上下文用量
5. 验证配置弹窗：切换 provider 后正常对话
6. 验证清除历史功能
7. 验证手动 Compact 功能
8. `python main.py -s` 终端模式正常运行
9. `python main.py -c "msg"` 命令行模式正常运行

### 7.2 回归验证

- Agent 循环行为与 Qt 版本一致（同 provider/model 下输出相同）
- 工具执行结果一致
- Compact 行为一致

### 7.3 性能验证

- Flet UI 响应流畅，消息渲染不卡顿
- 流式文本增量更新顺畅
- 长时间对话后内存稳定

---

## 8. 风险与缓解

| 风险 | 缓解 |
|------|------|
| Flet Markdown 不支持某些 GFM 语法 | 预处理降级不支持的语法（如复杂表格） |
| `run_stream` 缺少 compact 管线 | 在 while 循环顶部添加 compact 调用 |
| Flet 桌面端 Windows 兼容性 | Flet 官方支持 Windows，提前测试 |
| cancel 功能需在 Agent 循环中插入检查点 | 使用 asyncio.Event，在每轮循环和工具执行前检查 |
