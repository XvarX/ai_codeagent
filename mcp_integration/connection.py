"""MCP connection manager — mirrors src/services/mcp/client.ts connectToServer."""

import asyncio
import logging
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from tools.base import Tool, ToolContext
from mcp_integration.config import MCPServerConfig

logger = logging.getLogger(__name__)


class MCPToolWrapper(Tool):
    """Wraps an MCP server tool as a project Tool.

    Mirrors src/tools/MCPTool/MCPTool.ts with runtime name/description
    overrides from the discovered tool.
    """

    def __init__(self, server_name: str, tool, session: ClientSession):
        self.name = f"mcp__{server_name}__{tool.name}"
        self.description = tool.description or f"MCP tool: {tool.name}"
        self.parameters = tool.inputSchema if hasattr(tool, "inputSchema") else {}
        self._server_name = server_name
        self._tool_name = tool.name
        self._session = session

    async def call(self, input: dict, context: ToolContext) -> str:
        try:
            result = await self._session.call_tool(self._tool_name, arguments=input)
            parts = []
            for item in result.content:
                if hasattr(item, "text"):
                    parts.append(item.text)
                else:
                    parts.append(f"[{item.type}]")
            return "\n".join(parts) if parts else "(empty result)"
        except Exception as e:
            return f"MCP tool error [{self._server_name}/{self._tool_name}]: {e}"


class MCPConnectionManager:
    """Connects to MCP servers, discovers tools.

    connect_all() starts background tasks for each server.
    get_tools() returns discovered tools for registry injection.
    """

    def __init__(self, servers: list[MCPServerConfig]):
        self._servers = servers
        self._tools: list[MCPToolWrapper] = []
        self._tasks: list[asyncio.Task] = []

    async def connect_all(self) -> None:
        """Start background connection tasks and wait for all to connect."""
        if not self._servers:
            return
        events = [asyncio.Event() for _ in self._servers]
        for server, ev in zip(self._servers, events):
            task = asyncio.create_task(self._run_server(server, ev))
            self._tasks.append(task)
        # Wait for all connections to complete (or fail)
        await asyncio.gather(*(ev.wait() for ev in events))

    async def _run_server(self, config: MCPServerConfig, ready: asyncio.Event) -> None:
        """Connect to one server and hold the session open indefinitely."""
        server_name = config.name
        try:
            params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env=config.env if config.env else None,
            )

            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    tools_result = await session.list_tools()
                    for tool in tools_result.tools:
                        self._tools.append(MCPToolWrapper(server_name, tool, session))

                    logger.info(
                        f"MCP '{server_name}': {len(tools_result.tools)} tools"
                    )
                    ready.set()

                    # Hold session open until cancelled
                    await asyncio.Event().wait()

        except asyncio.CancelledError:
            ready.set()
        except Exception as e:
            logger.warning(f"MCP '{server_name}': failed — {e}")
            ready.set()

    def get_tools(self) -> list[MCPToolWrapper]:
        return list(self._tools)

    async def close_all(self) -> None:
        for task in self._tasks:
            task.cancel()
