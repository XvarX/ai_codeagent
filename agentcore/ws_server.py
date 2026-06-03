"""WebSocket server — bridges frontend <-> AgentController.

Start: python main.py --ws --port 18765
"""

import asyncio
import json
import logging
import re
from pathlib import Path

import websockets
from websockets.asyncio.server import serve, ServerConnection

from agentcore.config import AgentConfig
from agentcore.controller import AgentController, EventHandler

logger = logging.getLogger(__name__)


class WsEventHandler(EventHandler):
    """EventHandler that forwards all events as JSON over WebSocket.

    Sends two types of messages:
    - Raw events (thinking, text_delta) for real-time streaming
    - Formatted debug events (debug_event) for the debug panel
    """

    def __init__(self, ws: ServerConnection, controller: AgentController):
        self._ws = ws
        self._controller = controller
        self._pending_request_data = None
        self._pending_tool_calls: list[dict] = []

    async def _send(self, data: dict):
        try:
            payload = json.dumps(data, ensure_ascii=False)
            await self._ws.send(payload)
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            print(f"[ws_server] _send error: {e}")

    async def _send_debug(self, prefix: str, message: str, color: str,
                          event_data: dict | None = None,
                          group_key: str | None = None):
        print(f"[ws_server] debug_event: {prefix}")
        await self._send({
            "type": "debug_event",
            "prefix": prefix,
            "message": message,
            "color": color,
            "data": event_data,
            "group_key": group_key,
        })

    async def on_thinking(self):
        await self._send({"type": "thinking"})
        await self._send_debug(
            "[Send Tool Result]", "→ LLM  |  回传工具结果", "#8B5CF6")

    async def on_text_delta(self, token: str, reasoning: bool = False):
        await self._send({"type": "text_delta", "token": token, "reasoning": reasoning})

    async def on_tool_use(self, name: str, input_dict: dict, tool_use_id: str = ""):
        self._pending_tool_calls.append({
            "name": name, "input_dict": input_dict, "tool_use_id": tool_use_id,
        })
        await self._send({
            "type": "tool_use", "name": name, "input": input_dict, "id": tool_use_id,
        })

        # Pre-read old file for diff display
        if name in ("FileEdit", "FileWrite") and input_dict.get("file_path"):
            fp = Path(input_dict["file_path"])
            if not fp.is_absolute():
                fp = Path(self._controller.agent.cwd) / fp
            old = ""
            try:
                old = fp.read_text(encoding="utf-8")
            except (FileNotFoundError, IOError):
                pass
            self._pending_tool_calls[-1]["file_path"] = str(fp)
            self._pending_tool_calls[-1]["old_content"] = old

    async def on_tool_result(self, name: str, result: str, is_error: bool,
                             duration_ms: float = 0, tool_use_id: str = ""):
        color = "#EF4444" if is_error else "#10B981"
        preview = result[:500].replace("\n", " ")

        # Merge with pending tool call
        tc = self._pending_tool_calls.pop(0) if self._pending_tool_calls else None
        input_dict = tc["input_dict"] if tc else {}
        if not tool_use_id and tc:
            tool_use_id = tc.get("tool_use_id", "")

        call_detail = "\n".join(
            f"{k}: {str(v)[:200]}" for k, v in input_dict.items()
        )
        dur_str = f"{duration_ms:.0f}ms" if duration_ms else ""

        size_line = f"size: {len(result)} chars"
        try:
            from agentcore.tools.tool_result_storage import is_content_already_compacted
            if is_content_already_compacted(result):
                m = re.search(r'\[(\d+) chars saved', result)
                if m:
                    size_line = f"size: {len(result)} chars (original: {m.group(1)} chars)"
        except ImportError:
            pass

        status_icon = "✗" if is_error else "✓"
        message = (
            f"{call_detail}\n---\n"
            f"status: {'ERROR' if is_error else 'OK'}  |  {size_line}"
            f"{'  |  ' + dur_str if dur_str else ''}\n"
            f"{preview}"
        )

        # Gather diff data for FileEdit / FileWrite
        file_path = tc.get("file_path", "") if tc else ""
        old_content = tc.get("old_content", "") if tc else ""
        new_content = ""
        if name in ("FileEdit", "FileWrite") and file_path and not is_error:
            try:
                new_content = Path(file_path).read_text(encoding="utf-8")
            except (FileNotFoundError, IOError):
                pass

        await self._send({
            "type": "tool_result", "name": name, "result": result,
            "is_error": is_error, "duration_ms": duration_ms, "id": tool_use_id,
            "diff": {
                "file_path": file_path,
                "old_content": old_content,
                "new_content": new_content,
            } if file_path and old_content != new_content else None,
        })
        await self._send_debug(
            f"[Tool] {name} {status_icon}", message, color,
            event_data={
                "type": "Tool",
                "name": name,
                "input": input_dict,
                "result": result[:5000],
                "is_error": is_error,
                "duration_ms": duration_ms,
                "formatted": (
                    f"━━━ Tool Call ━━━\nTool: {name}\n\n" +
                    "\n".join(f"  {k}: {str(v)[:200]}" for k, v in input_dict.items()) +
                    f"\n\n━━━ Tool Result ━━━\n"
                    f"Status: {'ERROR' if is_error else 'OK'}\n"
                    f"Duration: {dur_str or 'N/A'}\n"
                    f"Size: {len(result)} chars\n\n{result[:5000]}"
                ),
            },
            group_key=f"tool:{tool_use_id}" if tool_use_id else None,
        )

    async def on_response_done(self, raw: dict):
        model = raw.get("model", "?")
        usage = raw.get("usage", {})
        if not usage and "raw_response" in raw:
            usage = raw["raw_response"].get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0) or 0
        completion_tokens = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0) or 0
        total_tokens = usage.get("total_tokens", 0) or (prompt_tokens + completion_tokens)

        pt_details = usage.get("prompt_tokens_details") or {}
        cache_read = pt_details.get("cached_tokens", 0) if isinstance(pt_details, dict) else 0

        msgs = self._controller.agent.messages
        final_text = raw.get("_text", "")
        tool_blocks = raw.get("_tool_use_blocks", [])

        resp_lines = [f"Model: {model}  |  Msgs: {len(msgs)}"]
        resp_lines.append(f"prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens}")
        if cache_read:
            resp_lines.append(f"cache hit: {cache_read} tokens ({cache_read * 100 // max(prompt_tokens, 1)}%)")
        if tool_blocks:
            resp_lines.append("Tool calls: " + ", ".join(t["tool_name"] for t in tool_blocks))
        else:
            text_preview = final_text[:200].replace("\n", " ")
            resp_lines.append(f"Text: {text_preview}")

        prefix = "[Final Response]" if not tool_blocks else "[Response]"
        color = "#059669" if not tool_blocks else "#10B981"

        resp_only = {k: v for k, v in raw.items() if k not in ("_request",)}

        await self._send({"type": "response_done", "raw": raw})
        await self._send({
            "type": "context_usage",
            "total_tokens": total_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        })
        await self._send_debug(
            prefix, "\n".join(resp_lines), color,
            event_data={
                "type": "Response",
                "model": model,
                "formatted": "\n".join(resp_lines),
                "text": final_text,
                "raw_json": json.dumps(resp_only, ensure_ascii=False, indent=2),
            },
            group_key=f"asst:{raw.get('id', '')}" if raw.get("id") else None,
        )

    async def on_done(self, final_text: str):
        await self._send({"type": "done", "final_text": final_text})

    async def on_error(self, message: str):
        await self._send({"type": "error", "message": message})
        await self._send_debug("[Error]", message, "#EF4444")

    async def on_compact_call(self, old_msg_count: int, pre_tokens: int):
        await self._send({
            "type": "compact_call", "old_msg_count": old_msg_count, "pre_tokens": pre_tokens,
        })
        await self._send_debug(
            "[Compact Call]", f"→ LLM  |  {old_msg_count} msgs  |  ~{pre_tokens} tokens",
            "#F59E0B", group_key="compact_call")

    async def on_compact(self, pre_tokens: int, post_tokens: int,
                         trigger: str, summary: str = ""):
        info = f"{trigger}  |  ~{pre_tokens} → ~{post_tokens} tokens"
        if summary:
            info += f"\n---\n{summary[:800]}"
        await self._send({
            "type": "compact", "pre_tokens": pre_tokens, "post_tokens": post_tokens,
            "trigger": trigger, "summary": summary,
        })
        await self._send_debug(
            "[Compact]", info, "#F59E0B",
            event_data={
                "type": "Compact",
                "formatted": info,
                "trigger": trigger,
                "pre_tokens": pre_tokens,
                "post_tokens": post_tokens,
            })

    async def on_snip(self, groups_removed: int, tokens_before: int, tokens_after: int):
        await self._send({
            "type": "snip", "groups_removed": groups_removed,
            "tokens_before": tokens_before, "tokens_after": tokens_after,
        })
        await self._send_debug(
            "[SnipCompact]",
            f"Snip removed {groups_removed} groups\n"
            f"tokens: ~{tokens_before} → ~{tokens_after}",
            "#94A3B8", group_key="snip")

    async def on_subagent_done(self, agent_id: str, status: str, result: str):
        await self._send({
            "type": "subagent_done", "agent_id": agent_id,
            "status": status, "result": result,
        })

    async def on_request(self, text: str, msg_count: int, est_tokens: int,
                         tools_count: int, model: str = ""):
        agent = self._controller.agent
        msg_lines = [f"Model: {model}"]
        msg_lines.append(f"Messages: {msg_count}  |  ~{est_tokens} tokens  |  {tools_count} tools")
        msg_lines.append(f"  [new] user: {text[:80]}")
        for i, m in enumerate(agent.messages[-5:]):
            role = m.role
            content_preview = (m.content or "")[:50].replace("\n", " ")
            if m.tool_use_id:
                msg_lines.append(f"  [{i}] tool({m.tool_use_id[:12]}): {content_preview}")
            else:
                msg_lines.append(f"  [{i}] {role}: {content_preview}")
        if len(agent.messages) > 5:
            msg_lines.append(f"  ... +{len(agent.messages) - 5} earlier messages")

        request_data = {
            "type": "Request",
            "provider": model,
            "model": model,
            "message_count": msg_count,
            "est_tokens": est_tokens,
            "tools_count": tools_count,
            "user_message": text,
            "formatted": "\n".join(msg_lines),
        }
        self._pending_request_data = request_data

        await self._send({
            "type": "request", "text": text, "msg_count": msg_count,
            "est_tokens": est_tokens, "tools_count": tools_count, "model": model,
        })
        await self._send_debug(
            "[Request]", "\n".join(msg_lines), "#569cd6",
            event_data=request_data, group_key="user")

    async def on_enqueued(self, from_name: str, message: str, source: str):
        await self._send({
            "type": "enqueued", "from_name": from_name, "message": message, "source": source,
        })
        await self._send_debug(
            f"[Msg from {from_name}]", message[:300], "#A855F7",
            event_data={
                "type": "InboxMessage",
                "from": from_name,
                "message": message,
                "formatted": f"From: {from_name}\n\n{message[:2000]}",
            })


async def _handle_client(websocket: ServerConnection, controller: AgentController):
    """Handle a single WebSocket client connection."""
    handler = WsEventHandler(websocket, controller)
    controller.handler = handler

    # Send initial debug events
    registry = controller.registry
    await websocket.send(json.dumps({
        "type": "connected", "version": "0.1.0",
    }))
    await handler._send_debug(
        "System",
        f"Provider: {controller.config.provider}  |  Model: {controller.provider.model or 'default'}\n"
        f"Tools: {', '.join(registry.get_tool_names())}\n"
        f"CWD: {controller.config.cwd or Path.cwd()}",
        "#569cd6")

    # MCP info
    mcp_info = controller.get_mcp_info()
    if mcp_info:
        svr_lines = [f"MCP: {mcp_info['server_count']} servers, {mcp_info['tool_count']} tools"]
        for s in mcp_info["servers"]:
            tool_names = ", ".join(t["name"] for t in s.get("tools", []))
            svr_lines.append(f"  {s['name']}: {tool_names}")
        await handler._send_debug("System", "\n".join(svr_lines), "#6366F1",
                                  event_data={"type": "MCP", "servers": mcp_info["servers"]})
    else:
        await handler._send_debug("System", "MCP: no servers configured", "#94A3B8")

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
                await handler._send_debug("[Stopped]", "用户中止了当前任务", "#EF4444")
            elif msg_type == "clear_history":
                controller.clear_history()
            elif msg_type == "reconfigure":
                from agentcore.config import AgentConfig as AC
                new_config = AC(**msg.get("config", {}))
                controller.reconfigure(new_config)
                await handler._send_debug(
                    "System",
                    f"Config updated: {new_config.provider} / {new_config.model}",
                    "#6366F1")
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
