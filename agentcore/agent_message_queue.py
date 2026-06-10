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
        self._queue: asyncio.Queue[tuple[str, str, str]] = asyncio.Queue()
        self._controller = controller
        self._consumer_task: asyncio.Task | None = None

    def enqueue(self, text: str, source: str = "user", room_id: str = "") -> None:
        """Enqueue a message. Starts the consumer if not running."""
        self._queue.put_nowait((text, source, room_id))
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
            text, source, room_id = await self._queue.get()
            try:
                sender = ""  # initialized for room/agent branches
                if source == "room":
                    room_match = re.match(r"\[Room: ([^\]]+)\]", text)
                    room_name = room_match.group(1).split("|")[0].strip() if room_match else "Unknown"
                    from_match = re.search(r"\[From: ([^\]]+)\]", text)
                    sender = from_match.group(1).strip() if from_match else "Unknown"
                    last_bracket = text.rfind("]")
                    msg_body = text[last_bracket + 1:].strip() if last_bracket >= 0 else text

                    # Log as request for debug panel consistency
                    agent = self._controller.agent
                    await self._controller.handler.on_request(
                        f"[Room: {room_name} | From: {sender}]\n{msg_body}",
                        len(agent.messages) + 1,
                        agent.est_tokens() + len(msg_body) // 2,
                        len(agent.registry.get_schemas()),
                        agent.provider.model or "",
                    )
                    await self._controller.handler.on_enqueued(sender, msg_body, "room")

                elif source == "agent":
                    m = re.match(r"\[Message from ([^\]]+)\]", text)
                    from_name = m.group(1) if m else "unknown"
                    msg_body = text[m.end():].strip() if m else text
                    await self._controller.handler.on_enqueued(
                        from_name, msg_body, source)
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
                    await self._controller.send_message(text, room_id=room_id)

                # Broadcast agent's response to other room members (not relayed messages)
                if source == "room" and room_id and "|relay" not in text:
                    agent = self._controller.agent
                    response_text = ""
                    for m in reversed(agent.messages):
                        if m.role == "assistant" and m.content:
                            response_text = m.content
                            break
                    if response_text:
                        from_name = getattr(agent, '_agent_name', '') or "unknown"
                        from_id = getattr(agent, '_agent_id', '')
                        mgr = getattr(agent, '_agent_manager', None)
                        if mgr and hasattr(mgr, '_rooms'):
                            room = mgr._rooms.get(room_id)
                            if room:
                                for aid in room.agent_ids:
                                    if aid != from_id:
                                        st = mgr.agents.get(aid)
                                        if st and st.message_queue:
                                            formatted = f"[Room: {room.name} | From: {from_name} (id:{from_id}) |relay]\n{response_text}"
                                            st.message_queue.enqueue(formatted, source="room", room_id=room_id)
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