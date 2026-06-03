"""Tests for AgentMessageQueue sequential processing."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from agentcore.agent_message_queue import AgentMessageQueue


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
    controller = MagicMock()
    controller._agent_lock = asyncio.Lock()

    async def slow_send(text):
        if text == "first":
            await asyncio.sleep(0.1)

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
