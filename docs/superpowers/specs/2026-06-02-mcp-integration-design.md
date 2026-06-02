# MCP 集成设计

## 背景

参照 Claude Code 源码的 MCP 实现，为项目添加 Model Context Protocol 支持。让 Agent 能连接外部 MCP 服务器，动态发现和调用其工具。

## 架构

```
.mcp.json → MCPConfigLoader → MCPServerConfig[]
                                    ↓
                        MCPConnectionManager
                           ├─ connect(stdio)
                           ├─ list_tools()
                           └─ MCPTool wrapper × N
                                    ↓
                            ToolRegistry.register()
                                    ↓
                            Agent (无感调用)
```

### 文件结构

```
mcp/
  __init__.py
  config.py       # .mcp.json 加载、解析、env 展开
  connection.py   # 连接管理、工具发现、工具包装
```

## 详细设计

### 1. 配置加载 `mcp/config.py`

**输入**：工作目录及其父目录的 `.mcp.json`，按"就近优先"合并。

**格式**：
```json
{
  "mcpServers": {
    "server-name": {
      "type": "stdio",
      "command": "python",
      "args": ["server.py"],
      "env": { "KEY": "value" }
    }
  }
}
```

**处理**：
- `MCPConfigLoader.load(cwd)` → `list[MCPServerConfig]`
- 遍历 `cwd` 向上找 `.mcp.json` 并合并
- `${VAR}` 环境变量展开
- `type` 默认 `stdio`（现阶段仅支持 stdio）
- 校验必填字段 `command`

### 2. 连接管理 `mcp/connection.py`

**`MCPConnectionManager`** 持有多服务器连接状态：

```python
class MCPConnectionManager:
    def __init__(self, servers: list[MCPServerConfig]):
        self._clients: dict[str, MCPClientSession]  # server_name → session

    async def connect_all(self) -> None:
        """并发连接所有服务器，失败不阻塞"""

    async def connect_server(self, config) -> MCPClientSession | None:
        """单个服务器连接 + 工具发现"""

    def get_all_tools(self) -> list[MCPTool]:
        """返回所有已连接服务器的工具列表"""

    async def close_all(self) -> None:
        """关闭所有连接"""
```

**连接流程**（单服务器）：
1. 创建 `StdioServerParameters(command, args, env)`
2. `stdio_client(params)` 获取 transport 读写流
3. `ClientSession(read, write)` 建立会话
4. `session.initialize()` 握手
5. `session.list_tools()` 发现工具
6. 每个工具包装成 `MCPTool` 实例

**依赖**：`mcp` Python SDK（`pip install mcp`）

### 3. 工具包装 `MCPTool`

```python
class MCPTool(Tool):
    def __init__(self, server_name: str, tool: ToolInfo, session):
        self.name = f"mcp__{server_name}__{tool.name}"
        self.description = tool.description or ""
        self.parameters = tool.inputSchema  # JSON Schema 直接透传
        self._server_name = server_name
        self._tool_name = tool.name
        self._session = session

    async def call(self, input: dict, context: ToolContext) -> str:
        result = await self._session.call_tool(self._tool_name, input)
        # result.content 是 [TextContent, ImageContent, ...]
        # 取所有 text 块拼接，非 text 块标注类型
        parts = []
        for item in result.content:
            if hasattr(item, 'text'):
                parts.append(item.text)
            else:
                parts.append(f"[{item.type}]")
        return "\n".join(parts)

    def is_read_only(self) -> bool:
        return False  # 保守默认，等 annotations 支持
```

- 命名规则 `mcp__server__tool`，与源码一致
- `inputSchema` 直接透传给 LLM，不做转换
- 调用走 `session.call_tool()`，结果转字符串回传

### 4. 集成到 Agent

在 `controller.py` 的 `_build_registry` 中：

```python
# 现有硬编码工具
registry.register_all([BashTool(), FileReadTool(), ...])

# MCP 动态工具
mcp_configs = MCPConfigLoader().load(cwd)
mcp_manager = MCPConnectionManager(mcp_configs)
await mcp_manager.connect_all()
for tool in mcp_manager.get_all_tools():
    registry.register(tool)
```

Agent 后续流程不变——LLM 看到工具列表、按名调用、`registry.get(name)` 找到 MCPTool、执行 `call()`。

## 错误处理

- 连接失败：记日志，跳过该服务器，继续启动
- 工具调用失败：返回 `{"error": "MCP tool error: ..."}` 文本
- 会话断开：下次调用时自动重连
- `.mcp.json` 不存在：正常跳过，不影响已有功能

## 验证

```bash
# 1. 安装依赖
pip install mcp

# 2. 创建测试 .mcp.json
echo '{"mcpServers":{"test":{"command":"echo","args":["hello"]}}}' > .mcp.json

# 3. 启动项目
python main.py
# 预期：启动时尝试连接 test 服务器，连接失败但不阻塞
```
