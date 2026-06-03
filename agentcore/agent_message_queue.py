"""AgentMessageQueue — per-agent sequential message queue."""

import asyncio
from agentcore.controller import AgentController


class AgentMessageQueue:
    """Per-agent sequential message queue.

    All message sources (user input, inter-agent SendMessage) call enqueue().
    A consumer coroutine processes messages one at a time via send_message(),
    guaranteeing the previous message is fully handled before the next begins.
    """

    def __init__(self, controller: AgentController):
        self._queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        self._controller = controller
        self._consumer_task: asyncio.Task | None = None

    def enqueue(self, text: str, source: str = "user") -> None:
        """Enqueue a message. Starts the consumer if not running."""
        self._queue.put_nowait((text, source))
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
            text, source = await self._queue.get()
            try:
                if source == "agent":
                    import re
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
                    await self._controller.send_message(text)
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