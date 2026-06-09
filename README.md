# AI Code Agent

一个全栈、多模型供应商的 AI 编程助手 —— 开源、可自托管，支持桌面 GUI 和命令行两种使用方式。

## 特性

- **多模型供应商** — 支持 Anthropic (Claude)、OpenAI (GPT)、智谱 (GLM)、DeepSeek，通过 YAML 配置即可切换
- **多智能体系统** — 主智能体 + 子智能体协同工作，支持前后台并行执行，智能体间可通过消息通信
- **多会话管理** — 同时运行多个对话，会话自动持久化到磁盘，随时恢复
- **桌面应用** — 基于 Tauri 2 + Vue 3 + TypeScript 的原生桌面应用，体验流畅
- **命令行模式** — 支持交互式 CLI 和一次性单命令模式，无需 GUI
- **上下文压缩** — LLM 驱动的对话摘要 + 智能裁剪，在上下文窗口限制内保持长对话
- **实时流式输出** — LLM 响应逐 token 推送到前端，即时反馈
- **MCP 支持** — 集成 Model Context Protocol，可连接外部工具服务器
- **技能系统** — 可加载项目级技能定义，教会 LLM 特定工作流
- **安全控制** — 可配置的每智能体工具白名单/黑名单、最大轮次/消息数限制
- **代码工具** — Bash、文件读写、编辑、Glob、Grep，覆盖代码助手核心操作

## 架构概览

```
┌─────────────────────────────────────────────────┐
│                   Tauri 2 (Rust)                 │
│  ┌───────────────────────────────────────────┐  │
│  │          Vue 3 + TypeScript 前端            │  │
│  │   ChatView | AgentPanel | DiffViewer ...   │  │
│  └──────────────┬────────────────────────────┘  │
│                 │ WebSocket                      │
│  ┌──────────────▼────────────────────────────┐  │
│  │        Python 后端 (agentcore)             │  │
│  │  ┌─────────────────────────────────────┐  │  │
│  │  │         Agent (while-True 循环)       │  │  │
│  │  │  LLM 调用 → 工具执行 → 结果反馈 → ... │  │  │
│  │  └──────────┬──────────────┬───────────┘  │  │
│  │  ┌──────────▼──────┐ ┌────▼───────────┐  │  │
│  │  │   Provider 层    │ │    Tool 层      │  │  │
│  │  │ Anthropic/OpenAI │ │ Bash/Read/Edit │  │  │
│  │  │ /GLM/DeepSeek   │ │ Write/Glob/Grep │  │  │
│  │  └─────────────────┘ └────────────────┘  │  │
│  └──────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 桌面壳 | Tauri 2 (Rust) |
| 前端 | Vue 3 (Composition API)、TypeScript、Vite 8、Tailwind CSS 4、Pinia 3 |
| 后端 | Python 3.11+ (asyncio、websockets) |
| LLM SDK | Anthropic SDK、OpenAI SDK |
| 配置 | YAML + 环境变量 |
| 打包 | PyInstaller + Tauri NSIS |

## 快速开始

### 前置条件

- Python 3.11+
- Node.js 18+
- Rust (如需构建 Tauri 桌面应用)

### 安装依赖

```bash
pip install -r requirements.txt
cd ui && npm install && cd ..
```

### 配置

```bash
mkdir -p .ai-code-agent
cp config.example.yaml .ai-code-agent/config.yaml
```

编辑 `.ai-code-agent/config.yaml`，填入你的 API Key：

```yaml
provider: glm          # anthropic | openai | glm | deepseek
model: "glm-4.7"       # 可选，留空使用默认模型

api_keys:
  anthropic: "sk-ant-xxx"
  openai: "sk-xxx"
  glm: "your-glm-key"
  deepseek: "sk-xxx"
```

`config.example.yaml` 可作为参考模板，实际运行时始终从 `.ai-code-agent/config.yaml` 加载配置。

### 运行

```bash
# 桌面应用（开发模式，含热重载）
dev.bat

# 仅启动后端 WebSocket 服务器
start_backend.bat

# 仅启动前端开发服务器
start_frontend.bat

# 命令行模式
python -m agentcore.main -s              # 交互式
python -m agentcore.main -c "你的问题"    # 单次命令
```

### 构建

```bash
build.bat    # 一键构建：PyInstaller 打包后端 → Tauri 打包桌面应用
```

产物在 `build/` 目录下。

## 项目结构

```
ai_codeagent/
├── agentcore/                # Python 后端核心
│   ├── agent.py              # 核心 Agent 循环
│   ├── controller.py         # Agent 生命周期控制器
│   ├── config.py             # 配置管理
│   ├── prompts.py            # 系统提示词构建
│   ├── agent_definitions.py  # 智能体类型定义
│   ├── subagent_manager.py   # 多智能体管理
│   ├── session_manager.py    # 会话管理
│   ├── session_store.py      # 会话持久化
│   ├── ws_server.py          # WebSocket 服务器
│   ├── providers/            # LLM 供应商适配层
│   │   ├── base.py           # 抽象基类
│   │   ├── anthropic.py      # Anthropic (Claude)
│   │   └── openai_compat.py  # OpenAI / GLM / DeepSeek
│   ├── tools/                # 工具实现
│   │   ├── base.py           # 工具抽象基类
│   │   ├── registry.py       # 工具注册中心
│   │   ├── bash.py           # Shell 命令执行
│   │   ├── file_read.py      # 文件读取
│   │   ├── file_edit.py      # 字符串替换编辑
│   │   ├── file_write.py     # 文件创建/覆盖
│   │   ├── glob.py           # 文件模式匹配
│   │   ├── grep.py           # 正则内容搜索
│   │   └── agent_tool.py     # 子智能体生成
│   ├── compact/              # 上下文压缩
│   ├── mcp_integration/      # MCP 协议集成
│   ├── skills/               # 技能系统
│   └── flet_ui/              # Flet 桌面 UI (备选)
├── ui/                       # Vue 3 + TypeScript 前端
│   ├── src/
│   │   ├── components/       # Vue 组件
│   │   ├── stores/           # Pinia 状态管理
│   │   ├── services/         # WebSocket 客户端
│   │   └── main.ts           # 应用入口
│   └── src-tauri/            # Tauri Rust 壳
├── tests/                    # 集成测试
├── docs/                     # 设计文档
├── config.example.yaml       # 配置示例
└── requirements.txt          # Python 依赖
```

## 内置智能体

| 智能体 | 类型 | 说明 |
|--------|------|------|
| **general-purpose** | 通用 | 执行各类编程任务，拥有全部工具权限 |
| **Explore** | 只读 | 代码库探索与搜索，仅允许读取类工具 |
| **Plan** | 只读 | 软件架构设计，输出实现方案而非编写代码 |

可在 `.myagent/agents/*.md` 中定义自定义智能体，格式为 YAML frontmatter + Markdown body。

## 配置参考

完整配置项见 `config.example.yaml`：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `provider` | 模型供应商 | `glm` |
| `model` | 模型名称（留空=供应商默认） | 空 |
| `api_keys.*` | 各供应商 API Key | 空 |
| `base_urls.*` | 各供应商 API 地址 | 官方地址 |
| `max_turns` | 单次对话最大工具调用轮次 | `50` |
| `max_messages` | 单次对话最大消息数 | `200` |
| `cwd` | 工作目录（留空=当前目录） | 空 |
| `verbose` | 打印调试信息 | `false` |

也可通过环境变量配置：`ANTHROPIC_API_KEY`、`OPENAI_API_KEY`、`GLM_API_KEY`、`DEEPSEEK_API_KEY`。

## 命令行选项

```
python -m agentcore.main              # 启动 Flet 桌面 GUI（默认）
python -m agentcore.main -s           # 交互式终端模式
python -m agentcore.main -c "..."     # 单次命令模式
python -m agentcore.main "..."        # 单次命令模式（简写）
python -m agentcore.main --ws         # 启动 WebSocket 服务器
python -m agentcore.main --ws --port 18765  # 指定端口
```

## 许可

MIT
