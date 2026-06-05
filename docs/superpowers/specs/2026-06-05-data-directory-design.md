# 统一数据目录设计

日期：2026-06-05

## 目标

为应用建立统一的数据存储目录结构，支持：
- 开发模式和打包模式使用相同的目录布局
- 关闭重启后完整恢复状态（对话、配置、运行时）
- 多对话管理，对话按项目分组
- 全局和项目两级 MCP/Skills 配置

## 路径解析

| 模式 | 根路径 | 决定者 |
|---|---|---|
| 开发 | `<项目根>/.ai-code-agent/` | Python 默认值 |
| 打包 | `%APPDATA%/.ai-code-agent/` | Tauri 通过 `--data-dir` 传入 |

Python 后端只认一个 `data_dir` 参数，不关心运行模式。Tauri 在打包模式下通过 `--data-dir` 传入 AppData 路径，开发模式下传项目根目录。

## 目录结构

### 全局：`.ai-code-agent/`

```
.ai-code-agent/
├── config.yaml                    # 用户配置（provider、API keys、模型）
├── config.local.json              # UI 偏好（主题、窗口位置、语言）
├── mcp/
│   └── servers.json               # 全局 MCP 服务器 [{name, command, args, env}]
├── skills/                        # 全局 skills
├── logs/
│   └── system/                    # 系统日志（启动、错误、性能）
└── store/
    ├── projects/
    │   └── {path-hash}/           # 项目路径的 SHA256 哈希前 16 位
    │       ├── meta.json          # {path, name, last_opened}
    │       └── sessions/
    │           └── {session-id}/
    │               ├── meta.json  # {title, created_at, model, msg_count}
    │               ├── messages.json    # 主 agent 对话历史
    │               ├── llm_log.json     # LLM 原始 request/response
    │               └── subagents/
    │                   └── {sub-id}/
    │                       ├── messages.json
    │                       └── llm_log.json
    └── projects.json              # 项目索引 [{hash, path, name, last_opened}]
```

### 项目级：`.myagent/`

每个被打开的项目根目录下：

```
.myagent/
├── mcp/
│   └── servers.json               # 项目专属 MCP 服务器
├── skills/                        # 项目专属 skills
└── config.yaml                    # 项目级配置覆盖（可选）
```

## 配置加载顺序

优先级从高到低：
1. 环境变量（`AGENT_PROVIDER`、`AGENT_API_KEY` 等）
2. 项目级 `.myagent/config.yaml`
3. 全局 `.ai-code-agent/config.yaml`
4. `config.example.yaml`
5. 代码默认值

MCP servers 和 skills 取**并集**，同名时项目级优先。

## 数据流

### 启动

1. Tauri 确定 data_dir（打包用 AppData，开发用项目根）
2. Tauri 启动 Python 后端，传入 `--data-dir` 和 `--port`
3. Python 读 `.ai-code-agent/config.yaml` 初始化配置
4. 前端通过 WebSocket 获取项目列表（`projects.json`）

### 选择项目

1. 前端发 `load_project(path)`
2. 后端查找或创建 `{path-hash}/` 目录
3. 返回该项目下的 session 列表
4. 同时加载项目级 `.myagent/` 的 MCP 和 skills

### 切换对话

1. 前端发 `load_session(id)`
2. 后端读取 `sessions/{id}/messages.json` 恢复到 Agent 实例
3. Agent 继续从恢复的消息历史开始对话

### 运行中

- 每条消息实时追加到 `messages.json`（append-only，避免丢数据）
- LLM 原始响应（含 token 用量、延迟等）追加到 `llm_log.json`
- 子 agent 的消息独立存储在 `subagents/{sub-id}/` 下

### 关闭

- Agent flush 所有待写数据
- 更新 `meta.json`（last_opened、msg_count 等）
- 保存 UI 状态到 `config.local.json`

## 日志策略

| 类型 | 位置 | 粒度 |
|---|---|---|
| 系统日志 | `.ai-code-agent/logs/system/` | 按天滚动 |
| LLM 交互日志 | `sessions/{id}/llm_log.json` | 跟 session 绑定 |
| 子 agent 日志 | `subagents/{sub-id}/llm_log.json` | 跟子 agent 绑定 |

## 需要改动的文件

| 文件 | 改动 |
|---|---|
| `ui/src-tauri/src/main.rs` | 打包模式传 `--data-dir %APPDATA%/.ai-code-agent`，开发模式传项目根 |
| `agentcore/config.py` | `from_yaml()` 接受 `data_dir`，从 `{data_dir}/config.yaml` 读取 |
| `agentcore/main.py` | 解析 `--data-dir` 参数，传给 AgentConfig |
| `agentcore/ws_server.py` | 新增项目/session 相关的 WebSocket 消息处理 |
| `agentcore/agent.py` | 新增消息实时持久化逻辑 |
| `.gitignore` | 加 `.ai-code-agent/` |

## session 管理设计

### 用户流程

1. 打开应用 → 显示最近打开的项目列表
2. 选择项目 → 显示该项目的 session 列表（最近使用在前）
3. 选择 session → 加载对话历史，继续对话
4. 点"新对话" → 创建新 session
5. 点"更多" → 浏览其他项目的 session

### session-id 格式

UUID v4，如 `550e8400-e29b-41d4-a716-446655440000`。

### path-hash 格式

项目路径 SHA256 哈希的前 16 位十六进制字符，如 `D:\space\myproject` → `a3f2b1c4d5e6f789`。
