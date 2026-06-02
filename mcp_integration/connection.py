"""MCP connection manager — mirrors src/services/mcp/client.ts connectToServer."""

import asyncio
import logging
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from tools.base import Tool, ToolContext
from mcp_integration.config import MCPServerConfig

logger = logging.getLogger(__name__)


class MCPToolWrapper(Tool):
    """Wraps an MCP server tool as a project Tool."""

    def __init__(self, server_name: str, tool, session: ClientSession):
        self.name = f"mcp__{server_name}__{tool.name}"
        self.description = tool.description or f"MCP tool: {tool.name}"
        self.parameters = tool.inputSchema if hasattr(tool, "inputSchema") else {}
        self._server_name = server_name
        self._tool_name = tool.name
        self._session = session

    @property
    def server_name(self) -> str:
        return self._server_name

    @property
    def tool_name(self) -> str:
        return self._tool_name

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
    """Connects to MCP servers, discovers tools, tracks per-server state."""

    def __init__(self, servers: list[MCPServerConfig]):
        self._servers = {s.name: s for s in servers}
        self._statuses: dict[str, str] = {}       # name → connecting|connected|failed|disconnected
        self._tools: list[MCPToolWrapper] = []
        self._server_tasks: dict[str, asyncio.Task] = {}
        self._stop_events: dict[str, asyncio.Event] = {}
        for name in self._servers:
            self._statuses[name] = "pending"

    async def connect_all(self) -> None:
        """Start background connection tasks and wait for all to connect."""
        events = {}
        for name in self._servers:
            ev = asyncio.Event()
            events[name] = ev
            self._stop_events[name] = asyncio.Event()
            task = asyncio.create_task(self._run_server(name, ev))
            self._server_tasks[name] = task
        if events:
            await asyncio.gather(*(ev.wait() for ev in events.values()))

    async def _run_server(self, name: str, ready: asyncio.Event) -> None:
        """Connect to one server and hold the session open."""
        config = self._servers[name]
        self._statuses[name] = "connecting"
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
                        self._tools.append(MCPToolWrapper(name, tool, session))

                    self._statuses[name] = "connected"
                    logger.info(f"MCP '{name}': {len(tools_result.tools)} tools")
                    ready.set()

                    # Hold session open until stop requested
                    await self._stop_events[name].wait()

        except asyncio.CancelledError:
            self._statuses[name] = "disconnected"
            ready.set()
        except Exception as e:
            self._statuses[name] = "failed"
            logger.warning(f"MCP '{name}': failed — {e}")
            ready.set()

    async def stop_server(self, name: str) -> None:
        """Stop a single MCP server."""
        if name in self._stop_events:
            self._stop_events[name].set()
        if name in self._server_tasks:
            self._server_tasks[name].cancel()
            try:
                await self._server_tasks[name]
            except asyncio.CancelledError:
                pass
        # Remove tools from this server
        self._tools = [t for t in self._tools if t.server_name != name]
        self._statuses[name] = "disconnected"

    async def restart_server(self, name: str) -> None:
        """Restart a stopped/failed MCP server."""
        if name not in self._servers:
            return
        await self.stop_server(name)
        self._stop_events[name] = asyncio.Event()
        ev = asyncio.Event()
        task = asyncio.create_task(self._run_server(name, ev))
        self._server_tasks[name] = task
        await ev.wait()

    def get_tools(self) -> list[MCPToolWrapper]:
        return list(self._tools)

    def get_all_statuses(self) -> dict[str, dict]:
        """Return {name: {status, tool_count, tools: [{name, description}]}}."""
        by_server: dict[str, list[dict]] = {}
        for t in self._tools:
            by_server.setdefault(t.server_name, []).append({
                "name": t.tool_name,
                "description": t.description,
            })
        result = {}
        for name in self._servers:
            result[name] = {
                "status": self._statuses.get(name, "unknown"),
                "tool_count": len(by_server.get(name, [])),
                "tools": by_server.get(name, []),
            }
        return result

    async def close_all(self) -> None:
        for task in self._server_tasks.values():
            task.cancel()
