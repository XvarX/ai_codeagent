"""WebSocket server — bridges frontend <-> SubagentManager.

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
from agentcore.subagent_manager import SubagentManager
from agentcore.agent_definitions import load_user_agents, AgentDefinition
from agentcore.compact.grouping import group_by_api_round

logger = logging.getLogger(__name__)


class WsEventHandler(EventHandler):
    """EventHandler that forwards all events as JSON over WebSocket.

    Sends two types of messages:
    - Raw events (thinking, text_delta) for real-time streaming
    - Formatted debug events (debug_event) for the debug panel

    Also stores debug entries for snapshot/replay when switching agents.
    """

    def __init__(self, ws: ServerConnection, controller: AgentController):
        self._ws = ws
        self._controller = controller
        self._pending_request_data = None
        self._pending_tool_calls: list[dict] = []
        self._has_pending_tool_results = False
        self._debug_entries: list[dict] = []
        self._entry_id = 0

    def set_controller(self, controller: AgentController):
        """Update the controller reference (used when switching agents)."""
        self._controller = controller

    def get_snapshot(self) -> dict:
        """Return current debug state for saving when switching away."""
        return {
            "debug_entries": list(self._debug_entries),
            "entry_id": self._entry_id,
        }

    def load_snapshot(self, snapshot: dict | None):
        """Restore debug state from snapshot. Used when switching to an agent
        that has previously captured events."""
        if snapshot and snapshot.get("debug_entries"):
            self._debug_entries = list(snapshot["debug_entries"])
            self._entry_id = snapshot.get("entry_id", len(self._debug_entries))
        else:
            self._debug_entries = []
            self._entry_id = 0

    def clear_entries(self):
        """Clear all stored debug entries."""
        self._debug_entries = []
        self._entry_id = 0

    async def _send(self, data: dict):
        try:
            payload = json.dumps(data, ensure_ascii=False)
            await self._ws.send(payload)
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            print(f"[ws_server] _send error: {e}")

    def _compute_group_idx(self, group_key: str | None) -> int | None:
        """Compute persistent group G-number matching Flet's sync_groups.

        Uses a two-level gi→gid mapping so that entries surviving compact/snip
        keep their original G-number while new groups get incremented IDs.
        """
        if not group_key:
            return None

        groups = group_by_api_round(self._controller.agent.messages)

        # Build ID → gi lookups from current messages
        asst_id_to_gi: dict[str, int] = {}
        tool_id_to_gi: dict[str, int] = {}
        user_msg_groups: list[int] = []
        for gi, g in enumerate(groups):
            for m in g:
                if m.role == "assistant" and m.id:
                    asst_id_to_gi[m.id] = gi
                elif m.role == "user" and m.tool_use_id:
                    tool_id_to_gi[m.tool_use_id] = gi
                elif m.role == "user" and not m.is_tool_result and not m.tool_use_id:
                    content = m.content or ""
                    if not content.startswith("[Context compressed"):
                        user_msg_groups.append(gi)

        # Rebuild persistent gi→gid map from surviving existing entries
        persistent: dict[int, int] = {}
        for entry in self._debug_entries:
            gid = entry.get("group_idx")
            if gid is None or gid < 0 or entry.get("opacity", 1.0) < 1.0:
                continue
            key = entry.get("group_key") or ""
            gi = None
            if key.startswith("asst:"):
                gi = asst_id_to_gi.get(key[5:])
            elif key.startswith("tool:"):
                gi = tool_id_to_gi.get(key[5:])
            if gi is not None:
                persistent[gi] = gid

        max_persistent = max(
            (e.get("group_idx", -1) for e in self._debug_entries
             if e.get("group_idx") is not None and e.get("group_idx", -1) >= 0
             and e.get("opacity", 1.0) >= 1.0),
            default=-1)
        next_gid = max_persistent + 1

        # Count already-assigned entries to skip
        user_idx = sum(1 for e in self._debug_entries
                       if e.get("group_key") == "user"
                       and e.get("group_idx") is not None
                       and e.get("opacity", 1.0) >= 1.0)

        # Compute gi for this entry
        gi = None
        if group_key == "user":
            if user_idx < len(user_msg_groups):
                gi = user_msg_groups[user_idx]
            else:
                gi = len(groups)  # new user message starts next group
        elif group_key.startswith("asst:"):
            gi = asst_id_to_gi.get(group_key[5:])
        elif group_key.startswith("tool:"):
            gi = tool_id_to_gi.get(group_key[5:])
            if gi is None:
                # Tool result not yet in messages — check tool_use_blocks on assistant
                for _gi, g in enumerate(groups):
                    for m in g:
                        for b in (getattr(m, "tool_use_blocks", None) or []):
                            if b.tool_use_id == group_key[5:]:
                                gi = _gi
                                break

        if gi is None:
            return None

        gid = persistent.get(gi, next_gid)
        return gid

    async def _send_debug(self, prefix: str, message: str, color: str,
                          event_data: dict | None = None,
                          group_key: str | None = None):
        print(f"[ws_server] debug_event: {prefix}")
        group_idx = self._compute_group_idx(group_key)
        # Store for snapshot (includes opacity for persistent gid mapping)
        entry = {
            "prefix": prefix,
            "message": message,
            "color": color,
            "data": event_data,
            "group_key": group_key,
            "group_idx": group_idx,
            "opacity": 1.0,
        }
        self._debug_entries.append(entry)
        self._entry_id += 1
        # Send to frontend
        await self._send({
            "type": "debug_event",
            "prefix": prefix,
            "message": message,
            "color": color,
            "data": event_data,
            "group_key": group_key,
            "group_idx": group_idx,
        })

    async def on_thinking(self):
        await self._send({"type": "thinking"})
        if self._has_pending_tool_results:
            await self._send_debug(
                "[Send Tool Result]", "→ LLM  |  回传工具结果", "#8B5CF6",
                group_key=self._last_tool_group_key)

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
        raw_preview = result[:20].replace("\n", " ")
        if len(result) > 20:
            raw_preview += "..."
        preview = raw_preview

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
        self._has_pending_tool_results = True
        tool_gk = f"tool:{tool_use_id}" if tool_use_id else None
        self._last_tool_group_key = tool_gk
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
            group_key=tool_gk,
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

        resp_lines = [f"Msgs: {len(msgs)}"]
        resp_lines.append(f"prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens}")
        if cache_read:
            resp_lines.append(f"cache hit: {cache_read} tokens ({cache_read * 100 // max(prompt_tokens, 1)}%)")
        if tool_blocks:
            resp_lines.append("Tool calls: " + ", ".join(t["tool_name"] for t in tool_blocks))
        else:
            text_preview = final_text[:20].replace("\n", " ")
            if len(final_text) > 20:
                text_preview += "..."
            resp_lines.append(f"Text: {text_preview}")

        prefix = "[Final Response]" if not tool_blocks else "[Response]"
        color = "#059669" if not tool_blocks else "#10B981"

        resp_only = {k: v for k, v in raw.items() if k not in ("_request",)}

        # Detail dialog shows full text; entry message shows truncated preview
        detail_lines = list(resp_lines)
        if final_text and not tool_blocks:
            detail_lines[-1] = f"Text:\n{final_text}"

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
                "formatted": "\n".join(detail_lines),
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
        msg_lines = [f"Messages: {msg_count}  |  ~{est_tokens} tokens  |  {tools_count} tools"]
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

    async def _do_compact(self, agent):
        """Run full LLM compaction, mirroring Flet's _do_compact."""
        from agentcore.compact.compact import compact_conversation
        from agentcore.compact.grouping import estimate_tokens

        # Check if already in a round or compacting
        if agent._loop_running:
            await self._send_debug(
                "[Compact]", "Cannot compact while agent is running", "#EF4444")
            return
        if getattr(agent, '_compacting', False):
            await self._send_debug(
                "[Compact]", "Already compacting", "#F59E0B")
            return

        agent._compacting = True
        pre = estimate_tokens(agent.messages)
        await self.on_compact_call(len(agent.messages), pre)

        try:
            result = await compact_conversation(
                agent.provider,
                agent.messages,
                agent.registry.get_schemas(),
                keep_recent_rounds=2,
            )
            if result.summary_messages:
                agent.messages = result.summary_messages + result.messages_to_keep
                agent._last_actual_tokens = result.post_tokens
                agent._compact_count = getattr(agent, '_compact_count', 0) + 1
                await self.on_compact(
                    pre, result.post_tokens,
                    f"manual (#{agent._compact_count})",
                    summary=result.summary_text,
                )
                self._detect_compacted(agent.messages)
                # Sync full debug state to frontend
                compacted_entries = [
                    {"prefix": e["prefix"], "message": e["message"],
                     "color": e["color"], "data": e.get("data"),
                     "group_key": e.get("group_key"),
                     "group_idx": e.get("group_idx"),
                     "opacity": e.get("opacity", 1.0)}
                    for e in self._debug_entries
                ]
                await self._send({
                    "type": "debug_sync",
                    "entries": compacted_entries,
                })
            else:
                await self.on_compact(pre, pre, "skipped (not enough messages)")
        except Exception as e:
            await self.on_compact(pre, pre, f"failed: {e}")
        finally:
            agent._compacting = False

    def _detect_compacted(self, messages: list):
        """Gray out debug entries whose messages were removed by compaction."""
        groups = group_by_api_round(messages)
        asst_ids: set[str] = set()
        tool_ids: set[str] = set()
        for g in groups:
            for m in g:
                if m.role == "assistant" and m.id:
                    asst_ids.add(m.id)
                elif m.role == "user" and m.tool_use_id:
                    tool_ids.add(m.tool_use_id)

        for entry in self._debug_entries:
            if entry.get("opacity", 1.0) < 1.0:
                continue
            key = entry.get("group_key") or ""
            removed = False
            if key.startswith("asst:"):
                removed = key[5:] not in asst_ids
            elif key.startswith("tool:"):
                removed = key[5:] not in tool_ids
            elif key == "user":
                # Gray user entries whose following asst/tool entry is grayed
                pass  # handled by cascade below
            if removed:
                entry["opacity"] = 0.4

        # Cascade: gray user entries whose next non-meta entry is grayed
        for i, entry in enumerate(self._debug_entries):
            if entry.get("group_key") != "user" or entry.get("opacity", 1.0) < 1.0:
                continue
            cascade = False
            for j in range(i + 1, len(self._debug_entries)):
                nk = self._debug_entries[j].get("group_key") or ""
                if nk in (None, "", "compact", "compact_call"):
                    continue
                if self._debug_entries[j].get("opacity", 1.0) < 1.0:
                    cascade = True
                break
            if cascade:
                entry["opacity"] = 0.4

        # Cascade [Compact Call] entries whose [Compact] is grayed
        for i, entry in enumerate(self._debug_entries):
            if entry.get("group_key") != "compact" or entry.get("opacity", 1.0) >= 1.0:
                continue
            if i > 0 and self._debug_entries[i - 1].get("prefix") == "[Compact Call]":
                prev = self._debug_entries[i - 1]
                if prev.get("opacity", 1.0) >= 1.0:
                    prev["opacity"] = 0.4


async def _send_agent_list(ws: ServerConnection, manager: SubagentManager):
    """Send the full agent list to the frontend."""
    agents = []
    for aid, s in manager.agents.items():
        agents.append({
            "id": aid,
            "name": s.name,
            "status": s.status,
            "active": aid == manager.active_id,
        })
    await ws.send(json.dumps({"type": "agent_list", "agents": agents}, ensure_ascii=False))


async def _send_mcp_info(ws: ServerConnection, manager: SubagentManager):
    """Send MCP server info to the frontend."""
    active = manager.get_active()
    controller = active.controller
    mcp_info = controller.get_mcp_info()
    await ws.send(json.dumps({
        "type": "mcp_info",
        "mcp": mcp_info,
    }, ensure_ascii=False))


async def _handle_client(websocket: ServerConnection, manager: SubagentManager):
    """Handle a single WebSocket client connection."""
    # Create handler wired to the active (master) controller
    master_state = manager.get_active()
    controller = master_state.controller
    handler = WsEventHandler(websocket, controller)
    controller.handler = handler
    manager.master_handler = handler  # ensure subagent_done events reach WebSocket

    # Send initial debug events
    registry = controller.registry
    await websocket.send(json.dumps({
        "type": "connected", "version": "0.1.0",
    }))
    await handler._send_debug(
        "[System]",
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
        await handler._send_debug("[System]", "\n".join(svr_lines), "#6366F1",
                                  event_data={"type": "MCP", "servers": mcp_info["servers"]})
    else:
        await handler._send_debug("[System]", "MCP: no servers configured", "#94A3B8")

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
                # Ensure handler is wired to the current active controller
                active_state = manager.get_active()
                if handler._controller is not active_state.controller:
                    handler.set_controller(active_state.controller)
                    active_state.controller.handler = handler
                handler._has_pending_tool_results = False
                # Block input while compacting
                if getattr(active_state.controller.agent, '_compacting', False):
                    await handler._send_debug(
                        "[Blocked]", "正在压缩中，请稍候...", "#F59E0B")
                    continue
                text = msg.get("text", "")
                queue = active_state.message_queue
                if queue:
                    queue.enqueue(text, source="user")
                else:
                    await active_state.controller.send_message(text)

            elif msg_type == "cancel":
                active_state = manager.get_active()
                await active_state.controller.cancel()
                await handler._send_debug("[Stopped]", "用户中止了当前任务", "#EF4444")

            elif msg_type == "clear_history":
                active_state = manager.get_active()
                active_state.controller.clear_history()

            elif msg_type == "compact":
                active_state = manager.get_active()
                agent = active_state.controller.agent
                await handler._do_compact(agent)

            elif msg_type == "reconfigure":
                from agentcore.config import AgentConfig as AC
                new_config = AC(**msg.get("config", {}))
                active_state = manager.get_active()
                active_state.controller.reconfigure(new_config)
                await handler._send_debug(
                    "[System]",
                    f"Config updated: {new_config.provider} / {new_config.model}",
                    "#6366F1")

            elif msg_type == "switch_agent":
                target_id = msg.get("agent_id", "master")
                if target_id != manager.active_id and target_id in manager.agents:
                    # Save current snapshot to old state
                    old_state = manager.get_active()
                    old_state.debug_events = list(handler._debug_entries)

                    # Switch
                    manager.switch(target_id)

                    # Wire handler to the new active controller
                    new_state = manager.get_active()
                    new_state.controller.handler = handler
                    handler.set_controller(new_state.controller)

                    # Load stored debug events from the new state (captured while inactive)
                    if new_state.debug_events:
                        handler._debug_entries = list(new_state.debug_events)
                        handler._entry_id = len(new_state.debug_events)
                    else:
                        handler.clear_entries()

                    # Send full state dump to frontend
                    agent = new_state.controller.agent
                    messages_data = [
                        {"role": m.role, "content": m.content or ""}
                        for m in agent.messages
                    ]
                    await websocket.send(json.dumps({
                        "type": "agent_switched",
                        "agent_id": target_id,
                        "name": new_state.name,
                        "messages": messages_data,
                        "debug_events": new_state.debug_events or [],
                        "est_tokens": agent.est_tokens(),
                    }, ensure_ascii=False))

            elif msg_type == "spawn_agent":
                agent_name = msg.get("agent_name", "")
                user_prompt = msg.get("prompt", "")
                definition = AgentDefinition(
                    name=agent_name,
                    description=agent_name,
                    agent_type="user",
                    system_prompt="",
                    tools=None,
                    source="user",
                )
                agent_id = await manager.spawn(definition, user_prompt, background=True)
                await websocket.send(json.dumps({
                    "type": "agent_spawned",
                    "agent_id": agent_id,
                    "name": agent_name,
                    "status": "running",
                }))
                # Update agent list
                await _send_agent_list(websocket, manager)

            elif msg_type == "kill_agent":
                await manager.kill(msg.get("agent_id", ""))
                await _send_agent_list(websocket, manager)

            elif msg_type == "get_status":
                await _send_agent_list(websocket, manager)
                active = manager.get_active()
                controller = active.controller
                mcp_info = controller.get_mcp_info()
                await websocket.send(json.dumps({
                    "type": "status",
                    "busy": controller.agent._loop_running,
                    "config": {
                        "provider": controller.config.provider,
                        "model": controller.provider.model,
                    },
                    "usage": controller.estimate_usage(),
                    "agents": [
                        {
                            "id": aid,
                            "name": s.name,
                            "status": s.status,
                            "active": aid == manager.active_id,
                        }
                        for aid, s in manager.agents.items()
                    ],
                    "mcp": mcp_info,
                    "skills": getattr(controller.agent, 'skills_text', ''),
                }, ensure_ascii=False))

            elif msg_type == "mcp_stop":
                server_name = msg.get("server_name", "")
                controller = manager.get_active().controller
                if controller.mcp_manager:
                    await controller.mcp_manager.stop_server(server_name)
                await _send_mcp_info(websocket, manager)

            elif msg_type == "mcp_restart":
                server_name = msg.get("server_name", "")
                controller = manager.get_active().controller
                if controller.mcp_manager:
                    await controller.mcp_manager.restart_server(server_name)
                await _send_mcp_info(websocket, manager)

            elif msg_type == "shutdown":
                break
        except Exception as e:
            await websocket.send(json.dumps({
                "type": "error", "message": str(e),
            }, ensure_ascii=False))


async def _watch_files(root: Path, interval: float = 1.0) -> None:
    """Watch .py files under root for changes. Returns when a change is detected."""
    mtimes: dict[Path, float] = {}
    while True:
        for f in root.rglob("*.py"):
            try:
                mtime = f.stat().st_mtime
            except OSError:
                continue
            if f in mtimes and mtime != mtimes[f]:
                print(f"[reload] detected change in {f}")
                return
            mtimes[f] = mtime
        await asyncio.sleep(interval)


async def run_ws_server(config: AgentConfig, port: int = 18765, reload: bool = False):
    """Start WebSocket server. Called from main.py --ws mode."""

    watch_root = Path(__file__).parent

    while True:
        user_agents = load_user_agents(config.cwd)
        manager = SubagentManager(config, user_agents)

        # Connect MCP for master
        master_state = manager.agents["master"]
        await master_state.controller.connect_mcp()

        async def handler(websocket):
            await _handle_client(websocket, manager)

        logger.info(f"WebSocket server listening on ws://127.0.0.1:{port}")
        print(f"WebSocket server listening on ws://127.0.0.1:{port}")
        if reload:
            print("[reload] watching for changes in agentcore/")

        server_task = asyncio.create_task(
            _serve_forever(handler, port)
        )
        if reload:
            watch_task = asyncio.create_task(_watch_files(watch_root))
            done, _ = await asyncio.wait(
                [server_task, watch_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            # Cancel whichever didn't finish
            for t in [server_task, watch_task]:
                if not t.done():
                    t.cancel()
            if watch_task in done:
                print("[reload] restarting server...")
                await asyncio.sleep(0.5)  # brief pause before restart
                continue
            break
        else:
            await server_task
            break


async def _serve_forever(handler, port: int):
    async with serve(handler, "127.0.0.1", port):
        await asyncio.Future()
