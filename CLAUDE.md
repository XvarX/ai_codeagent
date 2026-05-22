# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是 Claude Code 核心 Agent 架构的 Python 重构版——一个多 provider、可离线使用的编码 Agent 框架。从 Claude Code TypeScript 源码提取核心 Agent 循环、工具系统和 Provider 抽象层，用 Python 重新实现。

## 运行方式

```bash
# 安装依赖
pip install -r requirements.txt

# TUI 双面板界面（默认）
python main.py

# 终端交互模式
python main.py -s

# 单次命令行模式
python main.py -c "你的消息"
# 或简写
python main.py "你的消息"
```

退出交互模式：`/exit` 或 `/quit`；清除对话历史：`/clear`

## 配置

`config.yaml` 是主配置文件，支持 `anthropic | openai | glm | deepseek` 四种 provider。环境变量可覆盖 YAML 配置（优先级：环境变量 > YAML > 默认值）：

| 环境变量 | 用途 |
|---|---|
| `AGENT_PROVIDER` | 覆盖 provider |
| `AGENT_API_KEY` | 覆盖 API key |
| `AGENT_MODEL` | 覆盖模型 |
| `AGENT_BASE_URL` | 覆盖 base URL |
| `AGENT_CWD` | 覆盖工作目录 |
| `AGENT_MAX_TURNS` | 最大 agent 轮次 |
| `AGENT_MAX_MESSAGES` | 最大消息数 |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GLM_API_KEY` / `DEEPSEEK_API_KEY` | 按 provider 的 API key |

## 架构：三层结构

```
Agent (agent.py)         — 会话管理、while-true 循环、消息历史
  ├─ Provider (providers/) — LLM API 调用、流式响应、tool_use 块解析
  └─ Tools (tools/)        — Bash/FileRead/FileEdit/FileWrite/Glob/Grep
```

### Agent 层（`agent.py`）

`Agent` 类持有 provider、ToolRegistry、消息历史和 cwd。`run(user_message)` 方法实现核心 while-true 循环：
1. 构建 system prompt + tools schema，调 LLM
2. 若响应无 `tool_use_blocks` → 终止，返回文本
3. 若有 tool_use 块 → 逐一执行工具，将结果追加到消息历史，循环回步骤 1
4. 达到 `max_turns`（默认 50）时强制终止

消息在多次 `run()` 调用间持久化（同一 Agent 实例维护完整对话历史）。超过 `max_messages` 时保留最后 N 条（naive snip）。

Agent 暴露三个回调钩子供 UI 层使用：`on_thinking`、`on_tool_call`、`on_tool_result`。

### Provider 层（`providers/`）

- **`BaseProvider`**（`providers/base.py`）：抽象基类，定义 `async call(messages, tools, system) -> tuple[Message, list[ToolUseBlock]]` 接口
- **`AnthropicProvider`**（`providers/anthropic.py`）：使用 Anthropic Python SDK，原生 tool_use 内容块，流式调用
- **`OpenAICompatProvider`**（`providers/openai_compat.py`）：使用 OpenAI SDK，通过 function calling 协议支持 OpenAI / GLM / DeepSeek

### 工具层（`tools/`）

- **`Tool`**（`tools/base.py`）：抽象基类，定义 `name`、`description`、`parameters`（JSON Schema）和 `call(input, context)` 方法
- **`ToolContext`**：传递给工具执行的数据类（含 cwd 和 messages）
- **`ToolRegistry`**（`tools/registry.py`）：管理工具注册、按名称查找、schema 序列化
- **六个内置工具**：`Bash`、`FileRead`、`FileEdit`、`FileWrite`、`Glob`、`Grep`
- `FileRead`、`Glob`、`Grep` 标记为只读（`is_read_only() == True`），为后续权限检查做准备

### System Prompt 构建（`prompts.py`）

通过两根管道发给 LLM：
- **管道一（文本）**：告知模型角色、任务、可用工具及使用偏好（优先专用工具而非 Bash）
- **管道二（结构化）**：每个工具的 JSON Schema 定义，使 LLM 能发出结构化 tool call

### 数据类型（`core_types.py`）

- `Message(role, content, tool_use_blocks, tool_use_id)` — 对话消息，支持 tool_result 标记
- `ToolUseBlock(tool_use_id, tool_name, input)` — LLM 返回的工具调用块
- `ToolResult(content, is_error)` — 工具执行结果
- `PermissionResult(allowed, reason)` — 权限检查结果（预留）

### 与 Claude Code TypeScript 源码的对应关系

| 概念 | Claude Code (TS) | 本项目 (Python) |
|---|---|---|
| Agent 循环 | `query.ts` / `QueryEngine.ts` | `agent.py` / `Agent` |
| LLM 调用 | `services/api/claude.ts` | `providers/` / `BaseProvider` |
| 工具系统 | `Tool.ts` / `tools.ts` | `tools/` / `Tool` + `ToolRegistry` |
| System Prompt | `constants/prompts.ts` | `prompts.py` |
| 终止判断 | `needsFollowUp` (query.ts:1062) | `if not tool_use_blocks: return` |

## 设计文档

`docs/specs/` 和 `docs/plans/` 目录下包含中文架构设计文档和实施计划（2026-05-19），记录了详细的架构决策和实现步骤。
