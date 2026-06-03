# Vue 3 + Electron 前端迁移设计

**日期:** 2026-06-03
**状态:** 待实施

## 目标

将当前 Flet 前端迁移到 Vue 3 + Electron，保留 Python Agent 后端不变。
功能全部对等迁移，不增减功能。同时将 Python 代码重构到 `agentcore/` 目录，清理根目录。

## 目录结构

```
ai_codeagent/
├── agentcore/          ← Python Agent 核心（从根目录迁入）
│   ├── __init__.py
│   ├── main.py
│   ├── agent.py
│   ├── controller.py
│   ├── core_types.py
│   ├── prompts.py
│   ├── config.py
│   ├── events.py
│   ├── ws_server.py    ← 新增
│   ├── providers/
│   ├── tools/
│   ├── compact/
│   ├── skills/
│   ├── mcp_integration/
│   ├── subagent_manager.py
│   ├── agent_message_queue.py
│   └── tests/
├── ui/                 ← Vue 3 + Electron
│   ├── src/
│   │   ├── components/
│   │   ├── stores/
│   │   ├── services/
│   │   ├── App.vue
│   │   └── main.ts
│   ├── electron/
│   │   └── main.ts
│   ├── package.json
│   └── vite.config.ts
├── docs/
├── build/              ← 打包产物
├── config.yaml
├── requirements.txt
└── README.md
```

## 通信层：WebSocket 协议

Python 后端启动 WebSocket server（`websockets` 库），Electron 前端连接。
所有消息为 JSON 格式，通过 `type` 字段区分。

### 前端 → 后端 (client events)

| type | 字段 | 用途 |
|------|------|------|
| `send_message` | `text: string` | 发送用户消息 |
| `cancel` | — | 取消当前任务 |
| `clear_history` | — | 清除对话历史 |
| `reconfigure` | `config: object` | 更新 Agent 配置 |
| `switch_agent` | `agent_id: string` | 切换当前 Agent |
| `get_status` | — | 获取状态快照 |
| `shutdown` | — | 关闭后端 |

### 后端 → 前端 (server events)

| type | 字段 | 对应 EventHandler 方法 |
|------|------|----------------------|
| `connected` | `version: string` | 连接建立 |
| `thinking` | — | `on_thinking` |
| `text_delta` | `token, reasoning` | `on_text_delta` |
| `tool_use` | `name, input, id` | `on_tool_use` |
| `tool_result` | `name, result, is_error, duration_ms, id` | `on_tool_result` |
| `response_done` | `raw: object` | `on_response_done` |
| `done` | `final_text` | `on_done` |
| `error` | `message` | `on_error` |
| `compact_call` | `old_msg_count, pre_tokens` | `on_compact_call` |
| `compact` | `pre, post, trigger, summary` | `on_compact` |
| `snip` | `removed, before, after` | `on_snip` |
| `subagent_done` | `agent_id, status, result` | `on_subagent_done` |
| `request` | `text, count, est, tools, model` | `on_request` |
| `enqueued` | `from_name, message, source` | `on_enqueued` |
| `status` | `busy, agents, config, usage` | 状态快照响应 |

## Electron 进程管理

### 启动流程

1. Electron 主进程 (`ui/electron/main.ts`) 启动
2. spawn Python 子进程：`python agentcore/main.py --ws --port <port>`
3. Python 后端启动 WebSocket server，发送 `{ type: "connected" }`
4. Electron 创建 BrowserWindow，加载 Vue 前端
5. Vue 前端连接 WebSocket

### 进程生命周期

- 子进程崩溃 → 弹通知 + 自动重启（最多 3 次）
- 窗口关闭 → kill 子进程 → 退出
- 菜单栏提供"重启后端"选项

### 开发模式 vs 生产模式

| | 开发 | 生产 |
|---|---|---|
| Vue 前端 | `vite dev` (localhost:5173) | 打包为静态文件 |
| Python 后端 | 手动 `python agentcore/main.py --ws` | Electron spawn |
| Electron | `electron .` | 打包为 exe |

### 打包策略

1. PyInstaller 将 `agentcore/` 编译为独立 `.exe`
2. electron-builder 将该 `.exe` 与 Vue 静态文件合并打包
3. 最终产物为单一安装包，用户无需安装 Python

```
build/dist/
└── ai-codeagent-1.0.0-win-x64/
    ├── ai-codeagent.exe          ← Electron
    ├── resources/
    │   ├── app.asar              ← Vue 前端
    │   └── agentcore.exe         ← Python 后端
    └── ...
```

## Vue 前端架构

**技术栈：** Vue 3 (Composition API) + Pinia + Vite + TypeScript

### 组件结构

| 组件 | 对应现有 Flet 文件 | 职责 |
|------|-------------------|------|
| `ChatView.vue` | chat_view.py | 消息列表、自动滚动 |
| `ChatBubble.vue` | chat_view.py 内部 | 用户/AI 气泡、Markdown 渲染 |
| `InputBar.vue` | input_bar.py | 多行输入、发送/停止按钮 |
| `DiffViewer.vue` | diff_viewer.py | 并排 diff、折叠上下文 |
| `DebugDrawer.vue` | debug_drawer.py | 调试面板、条目管理 |
| `AgentSidebar.vue` | agent_sidebar.py | Agent 列表、切换 |
| `ConfigDialog.vue` | config_dialog.py | Provider 配置弹窗 |
| `McpDialog.vue` | mcp_dialog.py | MCP 服务器弹窗 |
| `SkillDialog.vue` | skill_dialog.py | Skills 弹窗 |

### Pinia Store 划分

| Store | 职责 | 对应现有代码 |
|-------|------|-------------|
| `chat` | messages 列表、流式 token 拼接、thinking 状态 | app.py 中 `_on_text_delta` 等回调 |
| `agent` | busy 状态、当前 agent、agent 列表、config | app.py 中 `_busy`、`_active_agent_id` |
| `debug` | entry_records、分组 GX、灰色级联、重排 | debug_drawer.py 全部逻辑 |

### 数据流

```
WebSocket → agentWs.ts → 解析 type → dispatch 到 Pinia store → Vue 组件响应式更新
用户操作 → Pinia action → agentWs.ts.send() → WebSocket → Python 后端
```

### 主布局

顶部标题栏 + 左侧 AgentSidebar + 中间 ChatView + 右侧 DebugDrawer + 底部 InputBar。
CSS Grid 或 Flex 布局，和现有 Flet 布局一致。

## 后端改动

### ws_server.py（新增）

- 启动 WebSocket server，监听指定端口
- 接收前端 JSON 消息，路由到 AgentController 方法
- 将 EventHandler 回调转为 JSON 通过 WebSocket 发送
- 单客户端连接（后端同时只服务一个前端实例）

### main.py 双模式

- `python agentcore/main.py` — 现有 TUI 模式（向后兼容）
- `python agentcore/main.py --ws --port 18765` — WebSocket server 模式

### import 改写

所有 `from agent import X` 改为 `from agentcore.agent import X`。
机械替换，不改逻辑。`config.yaml` 路径改为 `../config.yaml`（从 agentcore/ 往上找）。

## 错误处理

- **WebSocket 断连** → 前端自动重连（指数退避，最大 30 秒），UI 显示"重连中"
- **Python 后端崩溃** → Electron 检测子进程退出，弹通知 + "重启"按钮
- **API 调用失败** → 后端发 `{ type: "error" }` ，前端 toast 提示

## 测试策略

- **WebSocket 协议** — Python pytest + websockets 库，不需要前端
- **Vue 组件** — Vitest 单测，mock WebSocket
- **不搞 E2E** — Electron E2E 成本高收益低

## 不做的事

- 不新增功能（持久化、主题切换等留给后续迭代）
- 不改 Agent 核心逻辑（agent.py、providers/、tools/ 不动）
- 不改 compact/snip 逻辑
- 保留 TUI 模式可用（`python agentcore/main.py` 无参数时）
