# Subagents 系统设计

## 目标

在现有单 Agent 架构上实现多 Agent 子系统：master agent 通过工具 spawn subagent，各 agent 独立对话、可后台运行、可互通消息。UI 侧边栏支持 agent 间自由切换。

## 架构

```
SubagentManager
├─ master: AgentController       ← 主 agent（复用现有）
├─ agents: dict[id, AgentController]
│   ├─ "master"                  ← 主 agent
│   ├─ "explore-1"               ← 后台运行的 Explore
│   └─ "review-1"                ← 后台运行的 Reviewer
├─ active_id: str                ← UI 当前显示的 agent
├─ inboxes: dict[id, asyncio.Queue]  ← 每个 agent 的消息接收队列
│
├─ spawn(definition, prompt) → 创建 AgentController
├─ kill(id)                  → cancel + 清理
├─ switch(id)                → 切换 UI 视图
└─ send(from, to, msg)       → 投递到目标 inbox
```

核心原则：一 Agent 一 Controller，messages / provider / tools 完全隔离。

## Agent 定义

### Built-in（硬编码）

| 类型 | 工具 | 说明 |
|------|------|------|
| `Explore` | FileRead, Glob, Grep, Bash(readonly) | 快速代码搜索 |
| `Plan` | FileRead, Glob, Grep, Agent | 架构设计，只读 |
| `general-purpose` | 全部（继承 master） | 通用任务 fallback |

### 用户自定义（`.myagent/agents/*.md`）

```markdown
---
name: code-reviewer
description: Review code for bugs
provider: glm
model: glm-5.1
tools: [FileRead, Grep]
---
You are a code reviewer...
```

YAML frontmatter 字段：
- `name` — agent 名称
- `description` — 描述
- `provider` — 使用哪个 LLM provider（不填继承 master）
- `model` — 覆盖该 provider 的默认 model
- `tools` — 白名单
- `disallowedTools` — 黑名单

加载优先级：built-in 先注册 → 用户自定义覆盖。

## 工具

### AgentTool

LLM 调用来 spawn subagent：

```python
{
    "description": "3-5 words describing the task",
    "prompt": "The task for the agent",
    "subagent_type": "explore | plan | general-purpose | custom_name",
    "run_in_background": true,  # 可选，后台运行
    "name": "my-agent",         # 可选，后续可 SendMessage
    "mode": "plan"              # 可选，权限模式
}
```

### SendMessageTool

Agent 间通信：

```python
{
    "to": "agent_name",
    "message": "content"
}
```

→ 投递到目标 inbox queue，目标 agent 的 run_stream 轮询注入。

## Agent 生命周期

```
spawn(definition, prompt)
  ├─ 解析 provider/model
  │   ├─ definition.provider → 用 config.api_keys[provider]
  │   ├─ definition.model    → 覆盖 provider 默认 model
  │   └─ 未指定 → 继承 master
  ├─ 裁剪工具集
  │   ├─ 默认：copy master.toolRegistry
  │   ├─ built-in：按预设裁剪
  │   └─ 自定义：tools/disallowedTools 规则
  ├─ 创建 AgentController(provider, registry, cwd)
  ├─ 创建 inbox asyncio.Queue
  ├─ run_in_background:
  │   └─ asyncio.create_task → 完成后通知 UI
  └─ 前台:
      └─ await → 结果返回调用方
```

通信流程：

```
AgentTool invoke
  → SubagentManager.spawn()
    → 创建 Controller + inbox
    → run_in_background / await
    → 运行时 SendMessage 投递到 inbox
    → 完成后返回结果
```

## UI — Agent 侧边栏

```
┌──┬──────────────────────────┐
│◀ │  [Master Agent]          │  ← 点 ◀ 折叠
│  │                           │
│  │  📍 Explore · running     │  ← 运行中
│  │    64/100 turns           │
│  │                           │
│  │  ✓ Review · done          │  ← 完成
│  │                           │
│  └───────────────────────────┘
│  主对话区                     │
└──────────────────────────────┘
```

- 无 subagent 时箭头不可见
- 有 subagent 时箭头出现，点击展开列表
- 点击 agent 名 → `switch(id)`，主视图切到对应对话
- 运行中显示状态动画，完成显示结果摘要

## 配置界面

现有配置对话框新增 "Agent 预设" 区域，配置 built-in agent 的 provider 和可用工具：

```yaml
# config.yaml
agent_presets:
  explore:
    provider: glm               # 不填继承默认
    allowed_tools: [FileRead, Glob, Grep, Bash]
  plan:
    provider: anthropic
    allowed_tools: [FileRead, Glob, Grep, Agent]
```

UI 上每个 built-in 类型一行：Provider 下拉 + 工具勾选。

## 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `agent_definitions.py` | 新建 | AgentDefinition + built-in 定义 + 加载器 |
| `subagent_manager.py` | 新建 | SubagentManager 核心 |
| `tools/agent_tool.py` | 新建 | Agent 工具 |
| `tools/send_message_tool.py` | 新建 | SendMessage 工具 |
| `flet_ui/agent_sidebar.py` | 新建 | 侧边栏 UI |
| `flet_ui/agent_config.py` | 新建 | Agent 预设配置 UI |
| `flet_ui/app.py` | 修改 | 集成 SubagentManager + 侧边栏 |
| `config.py` | 修改 | AgentConfig 加 agent_presets |
| `controller.py` | 修改 | Provider 构造支持多实例 |
| `flet_ui/config_dialog.py` | 修改 | 加 Agent 预设区域 |
