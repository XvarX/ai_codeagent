# My Agent — Python Agent Framework Design

## Context

从 Claude Code 源码提取核心 Agent 架构，用 Python 重写为一个多 provider、可离线使用的编码 Agent 框架。

目标：
1. 融会贯通 Claude Code 级别的 Agent 架构精髓
2. 在离线开发环境中替代 Claude Code 黑盒，自己可控

## Architecture

三层结构，对应 Claude Code 的 QueryEngine → query() → callModel()：

```
┌─ Agent (会话层) ──────────────────────────────┐
│  agent.py                                      │
│  - 持有消息历史、工具注册表、provider            │
│  - run(user_message) → while True 循环          │
│  对应: QueryEngine.ts + query.ts                │
└───────────────────────────────────────────────┘
         │
         ▼
┌─ Provider (API 层) ───────────────────────────┐
│  providers/                                     │
│    base.py      - BaseProvider 抽象              │
│    anthropic.py - Anthropic SDK                 │
│    openai_compat.py - OpenAI/GLM/DeepSeek       │
│  - 流式调用、tool schema 序列化、响应解析          │
│  对应: services/api/claude.ts + utils/api.ts     │
└───────────────────────────────────────────────┘
         │
         ▼
┌─ Tools (工具层) ──────────────────────────────┐
│  tools/                                         │
│    base.py    - Tool 抽象基类                    │
│    registry.py - ToolRegistry 注册/过滤          │
│    bash.py / file_read.py / file_edit.py /      │
│    file_write.py / glob.py / grep.py             │
│  对应: Tool.ts + tools.ts                       │
└───────────────────────────────────────────────┘
```

## File Structure

```
D:\space\labspace\my_agent\
├── main.py             # CLI 入口 + Agent 组装
├── agent.py            # Agent 核心循环
├── config.py           # 配置管理（provider 选择、model、参数）
├── prompts.py          # System Prompt 组装
├── types.py            # 共享类型 (Message, ToolUseBlock, ToolResult)
├── providers/
│   ├── __init__.py
│   ├── base.py          # BaseProvider ABC
│   ├── anthropic.py     # AnthropicProvider
│   └── openai_compat.py # OpenAIProvider (GLM/DeepSeek 兼容)
├── tools/
│   ├── __init__.py
│   ├── base.py          # Tool ABC
│   ├── registry.py      # ToolRegistry
│   ├── bash.py
│   ├── file_read.py
│   ├── file_edit.py
│   ├── file_write.py
│   ├── glob.py
│   └── grep.py
└── requirements.txt
```

## Core: Agent Loop (agent.py)

复刻 query.ts:307 的 while(true) 循环，终止判断完全由模型驱动：

```python
async def run(self, user_message: str) -> str:
    self.messages.append(Message(role="user", content=user_message))

    while True:
        # 1. 调 LLM（流式），边收边收集 tool_use 块
        assistant_msg, tool_use_blocks = await self.provider.call(
            messages=self.messages,
            tools=self.registry.get_schemas(),     # 管道二：API tools[]
            system=self._build_system_prompt(),    # 管道一：System Prompt 文本
        )

        self.messages.append(assistant_msg)

        # 2. 终止判断 — 复刻 query.ts:1062
        if not tool_use_blocks:
            # 模型给了纯文本，没有调工具 → 本轮结束
            return assistant_msg.content

        # 3. 执行工具 — 复刻 query.ts:1366
        for block in tool_use_blocks:
            tool = self.registry.get(block.tool_name)
            if tool is None:
                result = ToolResult(content=f"Error: unknown tool '{block.tool_name}'")
            else:
                result = await tool.call(block.input, self._make_context())
            self.messages.append(Message(
                role="user",
                content=result.content,
                tool_use_id=block.tool_use_id,
            ))

        # 4. 循环回去，把工具结果喂给 LLM
```

和源码的对照：

| Claude Code (query.ts) | Python (agent.py) |
|---|---|
| `while(true)` (307) | `while True:` |
| `toolUseBlocks` (557) | `tool_use_blocks: list` |
| `needsFollowUp = true` (834) | 收到 tool_use block 即 append |
| `if (!needsFollowUp)` (1062) | `if not tool_use_blocks: return` |
| `yield* handleStopHooks(...)` (1267) | 留 hook 接口，默认空实现 |
| `checkTokenBudget(...)` (1309) | 后续迭代，先不实现 |
| 错误恢复 (prompt-too-long) | 简化版：捕获异常 → 重试一次 |

## How Tools Reach the LLM

两条管道，和源码完全一致：

**管道一：System Prompt（文本）**
prompts.py → `build_system_prompt(tools)` → 文本描述
```
# Using your tools
- To read files use FileRead instead of cat, head, tail
- To edit files use FileEdit instead of sed or awk
- You can call multiple tools in a single response...
```

**管道二：API tools[]（结构化 schema）**
每个 Tool 序列化为 `{name, description, parameters: JSONSchema}`
Anthropic 使用 native tool_use；OpenAI/GLM/DeepSeek 使用 function calling

## Tool System

```python
class Tool(ABC):
    name: str
    description: str
    parameters: dict  # JSON Schema

    @abstractmethod
    async def call(self, input: dict, context: ToolContext) -> ToolResult: ...

    def is_enabled(self) -> bool: return True
    def is_read_only(self) -> bool: return False
```

内置工具：
- BashTool — 执行 shell 命令
- FileReadTool — 读文件
- FileEditTool — 精确字符串替换编辑
- FileWriteTool — 创建/覆写文件
- GlobTool — 文件名搜索
- GrepTool — 内容搜索

## Provider Abstraction

```
BaseProvider
  ├─ AnthropicProvider    (anthropic SDK, native tool_use blocks)
  └─ OpenAICompatProvider (openai SDK → OpenAI/GLM/DeepSeek)
```

统一接口：
```python
async def call(
    self, messages, tools, system
) -> tuple[Message, list[ToolUseBlock]]:
    """流式调用 LLM，返回 assistant 消息和解析出的 tool_use 块"""
```

## Configuration

```python
# config.py + 环境变量
agent = Agent(
    provider="anthropic",    # anthropic | openai | glm | deepseek
    model="claude-sonnet-4-6",
    tools=CODING_TOOLS,      # 预设工具集
    max_turns=50,            # 安全上限（兜底用，正常由模型驱动终止）
)
```

环境变量：
- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GLM_API_KEY` / `DEEPSEEK_API_KEY`
- `GLM_BASE_URL` / `DEEPSEEK_BASE_URL`（可选覆盖）

## What's In Scope

- Agent while 循环 + needsFollowUp 终止判断
- 6 个编码工具 (Bash, FileRead, FileEdit, FileWrite, Glob, Grep)
- 多 provider 支持 (Anthropic, OpenAI, GLM, DeepSeek)
- 流式 API 调用 + tool_use 块解析
- System Prompt 组装（两管道）
- 最简消息裁剪：超过 max_messages 条就从头裁掉（朴素 snip 替代）

## What's Out of Scope (for now)

- applyToolResultBudget（单消息预算控制）
- microcompact（工具结果数量清理）
- autocompact（LLM 摘要压缩）
- Stop hooks 完整实现
- Token budget nudging
- 权限系统
- Multi-agent / Team

## Verification

```bash
cd D:\space\labspace\my_agent
pip install -r requirements.txt
# 设置 API key 环境变量
python main.py "列出当前目录的文件"
```

预期：
1. Agent 调用 LLM → LLM 返回 Bash(ls)
2. Agent 执行 ls → 结果喂回 LLM
3. LLM 给纯文本回复 → 循环终止
4. 输出结果给用户
