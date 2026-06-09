# CLAUDE.md

此文件为 Claude Code 在此仓库中工作时提供指引。

## 项目概述

AI Code Agent —— 一个全栈、多供应商 AI 编程助手。Python 后端实现核心 Agent 循环，Vue 3 + Tauri 2 提供桌面 GUI，支持 CLI 交互模式。

**三种使用方式：**
- 桌面应用：`dev.bat`（Tauri + Vue 前端，开发模式）
- 终端交互：`python -m agentcore.main -s`
- 单次命令：`python -m agentcore.main -c "消息"`

## 开发命令

```bash
# Python 后端
pip install -r requirements.txt

# 前端
cd ui && npm install && cd ..

# 启动 WebSocket 后端（供前端连接）
python -m agentcore.main --ws --port 18765

# 启动前端开发服务器（Vite HMR）
cd ui && npm run dev

# 启动 Tauri 桌面应用（自动启动后端 + 前端）
dev.bat

# 运行测试
pytest tests/ -v

# 构建
build.bat
```

## 架构

```
Agent (agent.py)                   # 会话 + while-true 循环
  ├─ Provider (providers/)          # Anthropic/OpenAI/GLM/DeepSeek
  ├─ Tools (tools/)                 # Bash/Read/Edit/Write/Glob/Grep/Agent
  ├─ Compact (compact/)             # LLM 摘要 + token 预算 + snip
  ├─ SubAgentManager                # 多智能体协同（前后台、消息队列）
  ├─ SessionManager                 # 多会话并发管理
  └─ Skills (skills/)               # 可加载技能定义
```

### 各层要点

**Agent 层** (`agent.py`)：`Agent` 类持有 provider、ToolRegistry、消息历史、cwd。`run(user_message)` 实现核心 while-true 循环 —— 调 LLM → 检查 tool_use → 执行工具 → 结果反馈 → 循环。消息跨 `run()` 调用持久化。超限时触发自动压缩。

**Controller 层** (`controller.py`)：`AgentController` 包装 Agent，管理生命周期（取消、重连、MCP 集成、事件分发）。

**Provider 层** (`providers/`)：
- `AnthropicProvider` — Anthropic SDK，原生 tool_use 块
- `OpenAICompatProvider` — OpenAI SDK，通过 function calling 支持 OpenAI/GLM/DeepSeek

**工具层** (`tools/`)：每个工具继承 `Tool` ABC（name、description、parameters、call）。`ToolRegistry` 管理注册和 schema 生成。六个内置工具 + Agent 子智能体工具 + Skill 工具。

**上下文压缩** (`compact/`)：多层管道 —— auto-compact（LLM 摘要）→ snip（丢弃旧轮次）→ reactive compact（413 错误响应）→ tool result budget（限制单工具结果大小）。

**多智能体** (`subagent_manager.py` + `agent_message_queue.py`)：主智能体可 spawn 子智能体（前台/后台），独立 provider/model/tools。`SendMessage` 工具实现智能体间通信。

**会话管理** (`session_manager.py` + `session_store.py`)：`SessionSlot` 包装独立 AgentManager，持久化到 `.ai-code-agent/store/projects/`。

**WebSocket 服务器** (`ws_server.py`)：前端通过 JSON WebSocket API 连接后端，支持流式事件推送。

**前端** (`ui/`)：Vue 3 Composition API + Pinia + Tailwind CSS 4。WebSocket 客户端 (`agentWs.ts`) 连接后端。12 个组件覆盖聊天、调试、配置、MCP、技能、会话管理。

**Tauri 壳** (`ui/src-tauri/src/main.rs`)：管理 Python 后端子进程生命周期（启动/停止/重启），原生菜单栏。

## 关键文件

| 文件 | 职责 |
|------|------|
| `agentcore/agent.py` | 核心 Agent while-true 循环 |
| `agentcore/controller.py` | Agent 生命周期包装器 |
| `agentcore/config.py` | YAML + 环境变量配置加载 |
| `agentcore/prompts.py` | 系统提示词构建（双管道） |
| `agentcore/core_types.py` | Message / ToolUseBlock 数据类型 |
| `agentcore/subagent_manager.py` | 多智能体管理器 |
| `agentcore/session_manager.py` | 并发会话管理 |
| `agentcore/ws_server.py` | WebSocket JSON API |
| `agentcore/providers/anthropic.py` | Anthropic SDK 适配 |
| `agentcore/providers/openai_compat.py` | OpenAI/GLM/DeepSeek 适配 |
| `agentcore/tools/registry.py` | 工具注册中心 |
| `agentcore/tools/bash.py` | Bash 执行工具 |
| `agentcore/tools/file_edit.py` | 字符串替换文件编辑 |
| `agentcore/tools/file_write.py` | 文件创建/覆盖 |
| `agentcore/tools/file_read.py` | 文件读取 |
| `agentcore/tools/glob.py` | 文件模式匹配 |
| `agentcore/tools/grep.py` | 正则内容搜索 |
| `agentcore/tools/agent_tool.py` | 子智能体 spawn 工具 |
| `agentcore/compact/compact.py` | LLM 对话摘要 |
| `agentcore/compact/autoCompact.py` | 自动压缩触发逻辑 |
| `agentcore/skills/loader.py` | 技能定义加载 |
| `agentcore/mcp_integration/` | MCP 协议支持 |
| `agentcore/agent_definitions.py` | 内置智能体类型定义 |
| `ui/src/main.ts` | Vue 应用入口 |
| `ui/src/services/agentWs.ts` | WebSocket 客户端 |
| `ui/src/stores/agent.ts` | 智能体状态 (Pinia) |
| `ui/src/stores/chat.ts` | 聊天状态 (Pinia) |
| `ui/src/stores/session.ts` | 会话状态 (Pinia) |
| `ui/src-tauri/src/main.rs` | Tauri 入口，管理后端进程 |
| `ui/src-tauri/Cargo.toml` | Rust 依赖 |
| `ui/package.json` | Node 依赖和脚本 |

## 配置

主配置文件：`.ai-code-agent/config.yaml`（`config.example.yaml` 是参考模板）。

支持供应商：`anthropic` | `openai` | `glm` | `deepseek`

环境变量可覆盖 YAML 配置（优先级：环境变量 > YAML > 默认值）：

| 环境变量 | 用途 |
|----------|------|
| `AGENT_PROVIDER` | 覆盖 provider |
| `AGENT_API_KEY` | 覆盖 API key |
| `AGENT_MODEL` | 覆盖模型 |
| `AGENT_BASE_URL` | 覆盖 base URL |
| `AGENT_CWD` | 覆盖工作目录 |
| `AGENT_MAX_TURNS` | 最大轮次 |
| `AGENT_MAX_MESSAGES` | 最大消息数 |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GLM_API_KEY` / `DEEPSEEK_API_KEY` | 按供应商的 API key |

## 代码风格

- Python：类型提示（`ToolRegistry`、`AgentConfig`），async/await，dataclass
- Vue：Composition API（`<script setup lang="ts">`），Pinia stores，TypeScript 严格模式
- 测试：pytest + pytest-asyncio
- 工具名用 PascalCase 注册，snake_case 文件名

## 设计文档

`docs/specs/` — 架构设计文档（中文）
`docs/plans/` — 实现计划（中文）
