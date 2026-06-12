"""AgentMessageQueue — per-agent sequential message queue."""

import asyncio
import re
from agentcore.controller import AgentController


class AgentMessageQueue:
    """Per-agent sequential message queue.

    All message sources (user input, inter-agent SendMessage) call enqueue().
    A consumer coroutine processes messages one at a time via send_message(),
    guaranteeing the previous message is fully handled before the next begins.
    """

    def __init__(self, controller: AgentController):
        self._queue: asyncio.Queue[tuple[str, str, str, bool, dict]] = asyncio.Queue()
        self._controller = controller
        self._consumer_task: asyncio.Task | None = None

    def enqueue(self, text: str, source: str = "user", room_id: str = "", *, relay: bool = False, relay_meta: dict | None = None) -> None:
        """Enqueue a message. Starts the consumer if not running.

        Args:
            relay: True if this message is a relayed agent response, not a
                   user-initiated message.  Relay messages are delivered to the
                   agent but their responses are NOT re-broadcast to the room,
                   preventing infinite A↔B ping-pong loops.
            relay_meta: Structured metadata for room_relay frontend notification.
                       Only used when source="room". Contains:
                       - room_name, from_name, from_id, text, reply_to
        """
        self._queue.put_nowait((text, source, room_id, relay, relay_meta or {}))
        self._ensure_consumer()

    def _ensure_consumer(self) -> None:
        """Start the consumer loop if not already running."""
        if self._consumer_task is not None and not self._consumer_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
            self._consumer_task = loop.create_task(self._consumer_loop())
        except RuntimeError:
            pass

    async def _consumer_loop(self) -> None:
        """Process messages sequentially. Blocks on send_message per message."""
        while True:
            text, source, room_id, relay, relay_meta = await self._queue.get()
            try:
                sender = ""  # initialized for room/agent branches
                if source == "room":
                    room_match = re.match(r"\[Room: ([^\]]+)\]", text)
                    room_name = room_match.group(1).split("|")[0].strip() if room_match else "Unknown"
                    from_match = re.search(r"\|\s*From:\s*([^|\]]+)", text)
                    sender = from_match.group(1).strip() if from_match else "Unknown"
                    # Strip (id:xxx) suffix to get clean sender name
                    sender_name = re.sub(r"\s*\(id:[^)]*\)\s*$", "", sender).strip()
                    to_match = re.search(r"\|\s*To:\s*([^|\]]+)", text)
                    reply_to = to_match.group(1).strip() if to_match else ""
                    last_bracket = text.rfind("]")
                    msg_body = text[last_bracket + 1:].strip() if last_bracket >= 0 else text

                    # Check if this message was sent before our last broadcast —
                    # if so, the sender hadn't seen our reply yet at send time
                    msg_ts = relay_meta.get("ts", 0)
                    agent = self._controller.agent
                    last_broadcasts = getattr(agent, '_last_broadcast_ts', None) or {}
                    my_last_ts = last_broadcasts.get(room_id, 0)
                    if my_last_ts and msg_ts and msg_ts < my_last_ts:
                        text = (
                            "[⚠ 此消息发出时尚未看到你的最新回复，"
                            "对方已可能看到你的发言，无需重复回复]\n"
                            + text
                        )

                    # Notify frontend NOW — the agent is about to process this room message
                    if relay_meta:
                        ws_handler = getattr(self._controller, 'handler', None)
                        if ws_handler and hasattr(ws_handler, '_send'):
                            try:
                                await ws_handler._send({
                                    "type": "room_relay",
                                    "room_id": relay_meta.get("room_id", room_id),
                                    "room_name": relay_meta.get("room_name", room_name),
                                    "from_name": relay_meta.get("from_name", sender_name),
                                    "from_id": relay_meta.get("from_id", ""),
                                    "text": relay_meta.get("text", msg_body),
                                    "reply_to": relay_meta.get("reply_to", reply_to),
                                })
                            except Exception:
                                pass

                    # Log as request for debug panel consistency
                    agent = self._controller.agent
                    room_info = f"[Room: {room_name} | From: {sender}"
                    if reply_to:
                        room_info += f" | To: {reply_to}"
                    room_info += "]"
                    await self._controller.handler.on_request(
                        f"{room_info}\n{msg_body}",
                        len(agent.messages) + 1,
                        agent.est_tokens() + len(msg_body) // 2,
                        len(agent.registry.get_schemas()),
                        agent.provider.model or "",
                    )


                elif source == "agent":
                    m = re.match(r"\[Message from ([^(\]]+?)\s*\(id:([^)]*)\)\]", text)
                    from_name = m.group(1).strip() if m else "unknown"
                    from_id = m.group(2).strip() if m else ""
                    msg_body = text[m.end():].strip() if m else text
                    await self._controller.handler.on_enqueued(
                        from_name, msg_body, source)
                    # Push private_message to frontend for real-time display
                    ws_handler = getattr(self._controller, 'handler', None)
                    if ws_handler and hasattr(ws_handler, '_send'):
                        try:
                            await ws_handler._send({
                                "type": "private_message",
                                "from_name": from_name,
                                "from_id": from_id,
                                "text": msg_body,
                            })
                        except Exception:
                            pass
                elif source == "user":
                    agent = self._controller.agent
                    await self._controller.handler.on_request(
                        text,
                        len(agent.messages) + 1,
                        agent.est_tokens() + len(text) // 2,
                        len(agent.registry.get_schemas()),
                        agent.provider.model or "",
                    )
                async with self._controller._agent_lock:
                    await self._controller.send_message(text, room_id=room_id, source=source)
            except asyncio.CancelledError:
                break
            except Exception:
                pass
            self._queue.task_done()

    def cancel(self) -> None:
        """Cancel the consumer task."""
        if self._consumer_task and not self._consumer_task.done():
            self._consumer_task.cancel()
            self._consumer_task = None

    @property
    def pending_count(self) -> int:
        """Number of messages waiting in the queue."""
        return self._queue.qsize()