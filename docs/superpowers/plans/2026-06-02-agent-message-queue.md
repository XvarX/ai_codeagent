# Agent Message Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the scattered inbox/poller/drain system with a per-agent sequential message queue that guarantees messages are processed one at a time.

**Architecture:** Each agent holds an `AgentMessageQueue` with an internal `asyncio.Queue` and a consumer coroutine. All message sources (user input, inter-agent SendMessage) call `enqueue()`. The consumer loop calls `send_message()` sequentially — blocking until completion before taking the next message. The inbox poller and `run_stream` inbox drain are deleted entirely.

**Tech Stack:** asyncio, existing Agent/Controller/Handler infrastructure

---

### Task 1: Create AgentMessageQueue

**Files:**
- Create: `agent_message_queue.py`

- [ ] **Step 1: Write the AgentMessageQueue class**

Create `agent_message_queue.py` in the project root:

```python
"""AgentMessageQueue — per-agent sequential message queue."""

import asyncio
from controller import AgentController


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
                await self._controller.send_message(text)
            except asyncio.CancelledError:
                break
            except Exception:
                pass  # send_message handles its own errors via on_error
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
```

- [ ] **Step 2: Commit**

```bash
git add agent_message_queue.py
git commit -m "feat: add AgentMessageQueue for per-agent sequential message processing"
```

---

### Task 2: Wire queue into SubagentManager, remove inbox and poller

**Files:**
- Modify: `subagent_manager.py`
- Modify: `agent.py` (remove `inbox` attribute)
- Modify: `events.py` (remove `InboxMessageEvent`)

- [ ] **Step 1: Remove `inbox` from SubagentState, add `message_queue`**

In `subagent_manager.py`, change the `SubagentState` dataclass:

Replace:
```python
    inbox: asyncio.Queue
```
With:
```python
    message_queue: "AgentMessageQueue | None" = None
```

Also remove the `from SubagentManager` import of asyncio if it's only used for Queue (it's not — asyncio is used elsewhere, so keep the import).

- [ ] **Step 2: Remove `_inbox_poller` and `_start_poller`**

Delete the `_start_poller` method (around line 330) and the entire `_inbox_poller` method (around line 339-392).

Remove `self._start_poller()` call from `__init__` and delete `self._poller_task` attribute.

- [ ] **Step 3: Update `_create_master` — create queue instead of inbox**

Replace the inbox creation in `_create_master`:

Before:
```python
            inbox=asyncio.Queue(),
```
After:
```python
            message_queue=None,  # wired below
```

Before:
```python
        controller.agent.inbox = state.inbox
```
After:
```python
        from agent_message_queue import AgentMessageQueue
        queue = AgentMessageQueue(controller)
        state.message_queue = queue
```

Remove the `controller.agent._subagent_manager` and `controller.agent._agent_id` lines — these stay but move after the queue is created (they're already there, just make sure they remain).

- [ ] **Step 4: Update `spawn` — create queue instead of inbox**

Same pattern in `spawn`:

Before:
```python
            inbox=asyncio.Queue(),
```
After:
```python
            message_queue=None,
```

Before:
```python
        controller.agent.inbox = state.inbox
```
After:
```python
        from agent_message_queue import AgentMessageQueue
        queue = AgentMessageQueue(controller)
        state.message_queue = queue
```

- [ ] **Step 5: Replace `send_message_to_agent` — enqueue instead of inbox.put**

Replace the entire `send_message_to_agent` method:

Before:
```python
    async def send_message_to_agent(self, from_id: str, to_name_or_id: str, message: str):
        """Send a message from one agent to another via inbox."""
        from_state = self.agents.get(from_id)
        from_name_lower = from_state.name.lower() if from_state else ""
        if (to_name_or_id == from_id or
                to_name_or_id.lower() == from_name_lower):
            raise ValueError(f"Cannot send message to yourself ('{to_name_or_id}')")

        target = None
        for aid, st in self.agents.items():
            if aid == to_name_or_id or st.name.lower() == to_name_or_id.lower():
                target = aid
                break
        if target is None:
            raise ValueError(f"Agent '{to_name_or_id}' not found")

        from_state = self.agents.get(from_id)
        from_name = from_state.name if from_state else "unknown"
        await self.agents[target].inbox.put({
            "from": from_id,
            "from_name": from_name,
            "message": message,
        })
```

After:
```python
    async def send_message_to_agent(self, from_id: str, to_name_or_id: str, message: str):
        """Send a message from one agent to another via message queue."""
        from_state = self.agents.get(from_id)
        from_name_lower = from_state.name.lower() if from_state else ""
        if (to_name_or_id == from_id or
                to_name_or_id.lower() == from_name_lower):
            raise ValueError(f"Cannot send message to yourself ('{to_name_or_id}')")

        target_id = None
        for aid, st in self.agents.items():
            if aid == to_name_or_id or st.name.lower() == to_name_or_id.lower():
                target_id = aid
                break
        if target_id is None:
            raise ValueError(f"Agent '{to_name_or_id}' not found")

        from_name = from_state.name if from_state else "unknown"
        target_state = self.agents[target_id]
        if not target_state.message_queue:
            raise ValueError(f"Agent '{to_name_or_id}' has no message queue")
        formatted = f"[Message from {from_name}]\n{message}"
        target_state.message_queue.enqueue(formatted, source="agent")
```

- [ ] **Step 6: Add asyncio.Lock to AgentController**

The consumer loop and direct callers (`_run_background`, non-background `spawn`) must not call `send_message` concurrently. Use an `asyncio.Lock` on the controller.

In `controller.py`, add to `AgentController.__init__`:

```python
        self._agent_lock = asyncio.Lock()
```

- [ ] **Step 7: Update _run_background and spawn to acquire lock**

In `subagent_manager.py`, wrap `send_message` calls with the lock.

`_run_background`:

Before:
```python
            state.status = "running"
            await self._emit_request(state.controller, prompt)
            await state.controller.send_message(prompt)
```
After:
```python
            state.status = "running"
            await self._emit_request(state.controller, prompt)
            async with state.controller._agent_lock:
                await state.controller.send_message(prompt)
```

Non-background `spawn` path:

Before:
```python
                await self._emit_request(controller, prompt)
                await controller.send_message(prompt)
```
After:
```python
                await self._emit_request(controller, prompt)
                async with controller._agent_lock:
                    await controller.send_message(prompt)
```

- [ ] **Step 8: Update consumer loop to acquire lock**

Update `AgentMessageQueue._consumer_loop`:

```python
    async def _consumer_loop(self) -> None:
        """Process messages sequentially. Blocks on send_message per message."""
        while True:
            text, source = await self._queue.get()
            try:
                async with self._controller._agent_lock:
                    await self._controller.send_message(text)
            except asyncio.CancelledError:
                break
            except Exception:
                pass
            self._queue.task_done()
```

- [ ] **Step 10: Remove `inbox` from Agent class**

In `agent.py`, delete:
```python
        self.inbox: "asyncio.Queue | None" = None
```

- [ ] **Step 11: Remove inbox drain from `run_stream`**

In `agent.py`, delete the entire inbox drain block in `run_stream` (lines ~336-350):

```python
            # ── Drain inbox ──
            if self.inbox:
                while not self.inbox.empty():
                    try:
                        p = self.inbox.get_nowait()
                        from_name = p.get("from_name", "unknown")
                        message = p.get("message", "")
                        self.messages.append(Message(
                            role="user",
                            content=f"[Message from {from_name}]\n{message}",
                        ))
                        self.inbox.task_done()
                        yield InboxMessageEvent(from_name=from_name, message=message)
                    except Exception:
                        break
```

Also remove the same block in `run()` (non-stream version) if it exists.

Remove `InboxMessageEvent` from the import in `run_stream`:
```python
            InboxMessageEvent,
```

- [ ] **Step 12: Remove `InboxMessageEvent` from events.py**

Delete from `events.py`:
```python
@dataclass
class InboxMessageEvent:
    """An inbox message was drained and injected into the conversation."""
    from_name: str
    message: str
```

- [ ] **Step 13: Remove InboxMessageEvent handling from controller.py**

In `controller.py`:

Remove `InboxMessageEvent` from the import:
```python
    SubagentDoneEvent, InboxMessageEvent,
```
becomes:
```python
    SubagentDoneEvent,
```

Delete the handler dispatch block:
```python
                elif isinstance(event, InboxMessageEvent):
                    await self.handler.on_inbox_message(
                        event.from_name, event.message)
```

Delete the base handler method:
```python
    async def on_inbox_message(self, from_name: str, message: str): pass
```

- [ ] **Step 14: Commit**

```bash
git add agent_message_queue.py subagent_manager.py agent.py events.py controller.py
git commit -m "feat: add AgentMessageQueue, remove inbox/poller system"
```

---

### Task 3: Update _SubagentHandler and FletApp — remove inbox forwarding, update _on_send

**Files:**
- Modify: `subagent_manager.py` (_SubagentHandler)
- Modify: `flet_ui/app.py`

- [ ] **Step 1: Remove inbox-related code from _SubagentHandler**

In `subagent_manager.py`, in `_SubagentHandler`:

Delete the `_fwd_inbox_msg` attribute:
```python
        self._fwd_inbox_msg: callable | None = None
```

Delete the `on_inbox_message` method:
```python
    async def on_inbox_message(self, from_name: str, message: str):
        self._record(f"[Msg from {from_name}]", message[:200], "#A855F7",
                     group_key="user")
        if self._fwd_inbox_msg:
            self._fwd_inbox_msg(from_name, message)
```

- [ ] **Step 2: Remove inbox forwarding from FletApp._wire_handler_forwarding**

In `flet_ui/app.py`:

Delete from `_wire_handler_forwarding`:
```python
        handler._fwd_inbox_msg = app._on_inbox_message
```

Delete `'_fwd_inbox_msg'` from `_clear_handler_forwarding`'s for loop.

- [ ] **Step 3: Delete _on_inbox_message from FletApp**

Delete the entire method:
```python
    def _on_inbox_message(self, from_name: str, message: str):
        """Debug entry + chat bubble for received inter-agent messages."""
        self.chat_view.add_tool_label(
            f"[Msg from {from_name}]",
            message[:500],
        )
        self.debug_drawer.add_event(
            f"[Msg from {from_name}]",
            message[:300],
            "#A855F7",
            event_data={
                "type": "InboxMessage",
                "from": from_name,
                "message": message,
                "formatted": f"From: {from_name}\n\n{message[:2000]}",
            },
            group_key="user",
        )
        self.chat_view._try_update()
        self.debug_drawer._try_update()
```

- [ ] **Step 4: Update _on_send to use queue.enqueue**

In `flet_ui/app.py`, replace `_on_send`'s direct `send_message` call with queue enqueue.

The key change: instead of `self.page.run_task(self.controller.send_message, text)`, use the queue. Also move `add_user_message` and debug drawer entry creation into a handler that fires when the message is actually processed (not when enqueued).

Replace the bottom of `_on_send` (after building `request_data` and the log write):

Before:
```python
        self.page.run_task(self.controller.send_message, text)
```
After:
```python
        state = self.subagent_manager.agents.get(self.subagent_manager.active_id) if self.subagent_manager else None
        if state and state.message_queue:
            state.message_queue.enqueue(text, source="user")
        else:
            self.page.run_task(self.controller.send_message, text)
```

For the fallback (no queue), keep the old behavior. When queue exists, `enqueue` triggers the consumer which calls `send_message` sequentially.

But wait — `_on_send` also creates the `[Request]` debug entry and user message bubble BEFORE calling send_message. With the queue, the message might not be processed immediately. We need to move the UI updates (add_user_message, debug drawer [Request]) to when the message actually starts processing, not when it's enqueued.

The cleanest approach: keep `_on_send` as-is for the UI updates (show the user's message immediately), but replace `send_message` with `enqueue`. The user sees their message right away. When the queue processes it, the agent loop events flow through the handler.

Actually, looking at it more carefully: `_on_send` does:
1. `add_user_message(text)` — show user's bubble immediately ✓ (keep this, show even if queued)
2. `add_event("[Request]", ...)` — debug entry for the request ✓ (keep this)
3. `run_task(send_message, text)` — start processing

The issue: if the message is queued, the `[Request]` debug entry appears before the message is processed. The thinking animation starts. Then nothing happens until the queue processes the message. That's actually fine — the user sees their message and "thinking..." while waiting in queue.

So the change is minimal — just replace `run_task(send_message)` with `queue.enqueue()`:

Before:
```python
        self.page.run_task(self.controller.send_message, text)
```
After:
```python
        queue = self._get_active_queue()
        if queue:
            queue.enqueue(text, source="user")
        else:
            self.page.run_task(self.controller.send_message, text)
```

Add helper method:
```python
    def _get_active_queue(self):
        if not self.subagent_manager:
            return None
        state = self.subagent_manager.agents.get(self.subagent_manager.active_id)
        return state.message_queue if state else None
```

- [ ] **Step 5: Remove `_emit_request` and `_poller_deliver`**

Delete `_emit_request` static method from SubagentManager (no longer needed — queue handles everything).

Delete the `_poller_deliver` closure that was inside `_inbox_poller` (already deleted with the poller, but verify).

- [ ] **Step 6: Commit**

```bash
git add subagent_manager.py flet_ui/app.py
git commit -m "feat: wire AgentMessageQueue into UI and handlers, remove inbox forwarding"
```

---

### Task 4: Update SendMessageTool to use queue

**Files:**
- Modify: `tools/send_message_tool.py`

- [ ] **Step 1: Update call to use queue**

The tool currently calls `self._manager.send_message_to_agent()`, which we already updated in Task 2. No change needed to `send_message_tool.py` itself — it still calls the same method, and `send_message_to_agent` now enqueues via the queue.

- [ ] **Step 2: Verify and commit if changed**

If no changes needed, skip commit. Otherwise:
```bash
git add tools/send_message_tool.py
git commit -m "refactor: SendMessageTool routes through message queue"
```

---

### Task 5: Handle _on_agent_switch queue awareness

**Files:**
- Modify: `flet_ui/app.py`

- [ ] **Step 1: Ensure agent switch saves/restores queue state correctly**

When switching agents, the queue continues running in the background. The consumer loop is independent of the UI. No special handling needed — messages enqueued for an inactive agent will be processed by the consumer loop, and events will be recorded in `debug_events` (since the handler's forwarding is cleared when switching away).

Verify that `_on_agent_switch` doesn't try to interact with the queue directly. It should only deal with snapshots and replay — which it already does.

No code change needed for this task. Verify by inspection.

---

### Task 6: Integration test

**Files:**
- Create: `tests/test_message_queue.py`

- [ ] **Step 1: Write test for sequential message processing**

```python
"""Tests for AgentMessageQueue sequential processing."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from agent_message_queue import AgentMessageQueue


@pytest.mark.asyncio
async def test_messages_processed_sequentially():
    """Messages are processed one at a time, in order."""
    controller = MagicMock()
    controller._agent_lock = asyncio.Lock()
    controller.send_message = AsyncMock()

    queue = AgentMessageQueue(controller)
    queue.enqueue("first", source="user")
    queue.enqueue("second", source="user")

    # Give consumer time to process
    await asyncio.sleep(0.1)

    assert controller.send_message.call_count >= 1
    first_call = controller.send_message.call_args_list[0]
    assert first_call[0][0] == "first"

    # Wait for second message
    await asyncio.sleep(0.1)
    assert controller.send_message.call_count == 2
    second_call = controller.send_message.call_args_list[1]
    assert second_call[0][0] == "second"

    queue.cancel()


@pytest.mark.asyncio
async def test_enqueue_while_processing_queues():
    """Messages enqueued during processing wait their turn."""
    processing = asyncio.Event()
    controller = MagicMock()
    controller._agent_lock = asyncio.Lock()

    async def slow_send(text):
        if text == "first":
            await asyncio.sleep(0.1)
        processing.set()

    controller.send_message = slow_send

    queue = AgentMessageQueue(controller)
    queue.enqueue("first")
    await asyncio.sleep(0.01)  # let consumer pick up "first"

    queue.enqueue("second")
    await asyncio.sleep(0.2)  # wait for both to finish

    queue.cancel()


@pytest.mark.asyncio
async def test_cancel_stops_consumer():
    """Cancel stops the consumer loop."""
    controller = MagicMock()
    controller._agent_lock = asyncio.Lock()
    controller.send_message = AsyncMock()

    queue = AgentMessageQueue(controller)
    queue.enqueue("msg")
    await asyncio.sleep(0.05)

    queue.cancel()
    assert queue._consumer_task is None or queue._consumer_task.done()
```

- [ ] **Step 2: Run tests**

```bash
python -m pytest tests/test_message_queue.py -v
```

Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_message_queue.py
git commit -m "test: add AgentMessageQueue sequential processing tests"
```

---

### Task 7: Manual smoke test

- [ ] **Step 1: Launch Flet UI**

```bash
python main.py
```

- [ ] **Step 2: Test sequential user messages**

Send "hello", then immediately send "world". Verify both appear in order, second waits for first to complete.

- [ ] **Step 3: Test agent inter-agent messaging**

Send a message that triggers the Agent tool to spawn a subagent, then use SendMessage to send the subagent a follow-up. Verify the subagent processes both in order.

- [ ] **Step 4: Test agent switch during processing**

Start a long task on an agent, switch to another agent, send a message to the first agent via SendMessage, switch back. Verify the message was queued and processed.
