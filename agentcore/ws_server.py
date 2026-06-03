"""WebSocket server — bridges frontend <-> AgentController.

Start: python main.py --ws --port 18765
"""

import asyncio
import json
import logging
from pathlib import Path

import websockets
from websockets.asyncio.server import serve, ServerConnection

from agentcore.config import AgentConfig
from agentcore.controller import AgentController, EventHandler

logger = logging.getLogger(__name__)


class WsEventHandler(EventHandler):
    """EventHandler that forwards all events as JSON over WebSocket."""

    def __init__(self, ws: ServerConnection):
        self._ws = ws

    async def _send(self, data: dict):
        try:
            await self._ws.send(json.dumps(data, ensure_ascii=False))
        except websockets.exceptions.ConnectionClosed:
            pass

    async def on_thinking(self):
        await self._send({"type": "thinking"})

    async def on_text_delta(self, token: str, reasoning: bool = False):
        await self._send({"type": "text_delta", "token": token, "reasoning": reasoning})

    async def on_tool_use(self, name: str, input_dict: dict, tool_use_id: str = ""):
        await self._send({
            "type": "tool_use", "name": name, "input": input_dict, "id": tool_use_id,
        })

    async def on_tool_result(self, name: str, result: str, is_error: bool,
                             duration_ms: float = 0, tool_use_id: str = ""):
        await self._send({
            "type": "tool_result", "name": name, "result": result,
            "is_error": is_error, "duration_ms": duration_ms, "id": tool_use_id,
        })

    async def on_response_done(self, raw: dict):
        await self._send({"type": "response_done", "raw": raw})

    async def on_done(self, final_text: str):
        await self._send({"type": "done", "final_text": final_text})

    async def on_error(self, message: str):
        await self._send({"type": "error", "message": message})

    async def on_compact_call(self, old_msg_count: int, pre_tokens: int):
        await self._send({
            "type": "compact_call", "old_msg_count": old_msg_count, "pre_tokens": pre_tokens,
        })

    async def on_compact(self, pre_tokens: int, post_tokens: int,
                         trigger: str, summary: str = ""):
        await self._send({
            "type": "compact", "pre_tokens": pre_tokens, "post_tokens": post_tokens,
            "trigger": trigger, "summary": summary,
        })

    async def on_snip(self, groups_removed: int, tokens_before: int, tokens_after: int):
        await self._send({
            "type": "snip", "groups_removed": groups_removed,
            "tokens_before": tokens_before, "tokens_after": tokens_after,
        })

    async def on_subagent_done(self, agent_id: str, status: str, result: str):
        await self._send({
            "type": "subagent_done", "agent_id": agent_id,
            "status": status, "result": result,
        })

    async def on_request(self, text: str, msg_count: int, est_tokens: int,
                         tools_count: int, model: str = ""):
        await self._send({
            "type": "request", "text": text, "msg_count": msg_count,
            "est_tokens": est_tokens, "tools_count": tools_count, "model": model,
        })

    async def on_enqueued(self, from_name: str, message: str, source: str):
        await self._send({
            "type": "enqueued", "from_name": from_name, "message": message, "source": source,
        })


async def _handle_client(websocket: ServerConnection, controller: AgentController):
    """Handle a single WebSocket client connection."""
    handler = WsEventHandler(websocket)
    controller.handler = handler

    await websocket.send(json.dumps({
        "type": "connected", "version": "0.1.0",
    }))

    async for raw_message in websocket:
        try:
            msg = json.loads(raw_message)
        except json.JSONDecodeError:
            await websocket.send(json.dumps({
                "type": "error", "message": "Invalid JSON",
            }))
            continue

        msg_type = msg.get("type", "")
        try:
            if msg_type == "send_message":
                await controller.send_message(msg.get("text", ""))
            elif msg_type == "cancel":
                await controller.cancel()
            elif msg_type == "clear_history":
                controller.clear_history()
            elif msg_type == "reconfigure":
                from agentcore.config import AgentConfig as AC
                new_config = AC(**msg.get("config", {}))
                controller.reconfigure(new_config)
            elif msg_type == "get_status":
                await websocket.send(json.dumps({
                    "type": "status",
                    "busy": controller.agent._loop_running,
                    "config": {
                        "provider": controller.config.provider,
                        "model": controller.provider.model,
                    },
                    "usage": controller.estimate_usage(),
                }, ensure_ascii=False))
            elif msg_type == "shutdown":
                break
        except Exception as e:
            await websocket.send(json.dumps({
                "type": "error", "message": str(e),
            }, ensure_ascii=False))


async def run_ws_server(config: AgentConfig, port: int = 18765):
    """Start WebSocket server. Called from main.py --ws mode."""

    placeholder_handler = EventHandler()
    controller = AgentController(config, placeholder_handler)
    await controller.connect_mcp()

    async def handler(websocket):
        await _handle_client(websocket, controller)

    logger.info(f"WebSocket server listening on ws://127.0.0.1:{port}")
    print(f"WebSocket server listening on ws://127.0.0.1:{port}")
    async with serve(handler, "127.0.0.1", port):
        await asyncio.Future()  # run forever
