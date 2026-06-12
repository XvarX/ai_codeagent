"""Tests for BroadcastRoom tool and suppress_reply mechanism."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from agentcore.tools.broadcast_room_tool import BroadcastRoomTool
from agentcore.tools.base import Tool, ToolContext
from agentcore.agent_message_queue import AgentMessageQueue


# ── BroadcastRoomTool unit tests ──


def _make_manager(rooms=None, agents=None, master_handler=None):
    """Build a mock AgentManager with rooms and agents."""
    mgr = MagicMock()
    mgr._rooms = rooms or {}
    mgr.agents = agents or {}
    mgr.master_handler = master_handler
    return mgr


def _make_agent_state(agent_id, name="TestAgent", has_queue=True):
    """Build a mock AgentState."""
    state = MagicMock()
    state.controller = MagicMock()
    state.controller.agent = MagicMock()
    state.controller.agent._agent_name = name
    state.controller.agent._agent_id = agent_id
    state.controller.agent._current_room_id = ""
    state.controller.registry = MagicMock()
    state.controller.registry.get.return_value = None
    state.message_queue = MagicMock() if has_queue else None
    state.message_queue.enqueue = MagicMock()
    return state


def _make_room(room_id="room1", name="TestRoom", agent_ids=None):
    """Build a simple room-like object."""
    @dataclass
    class FakeRoom:
        id: str
        name: str
        agent_ids: list
        created_at: float = 0.0
    return FakeRoom(id=room_id, name=name, agent_ids=agent_ids or [])


@pytest.mark.asyncio
async def test_broadcast_success():
    """Successful broadcast enqueues to other agents and sends room_relay."""
    room = _make_room("r1", "Room1", ["A", "B", "C"])
    state_a = _make_agent_state("A", "Alice")
    state_a.controller.agent._current_room_id = "r1"
    state_b = _make_agent_state("B", "Bob")
    state_c = _make_agent_state("C", "Carol")

    # Agent A is the active agent — its controller.handler is the WsEventHandler
    ws_handler = MagicMock()
    ws_handler._send = AsyncMock()
    state_a.controller.handler = ws_handler

    mgr = _make_manager(
        rooms={"r1": room},
        agents={"A": state_a, "B": state_b, "C": state_c},
    )
    mgr.ws_handler = ws_handler

    tool = BroadcastRoomTool(mgr, "A")
    ctx = ToolContext(cwd="/tmp", messages=[])

    result = await tool.call({"message": "Hello room!"}, ctx)

    # Should have enqueued to B and C (not A)
    assert state_b.message_queue.enqueue.call_count == 1
    assert state_c.message_queue.enqueue.call_count == 1
    call_args = state_b.message_queue.enqueue.call_args
    assert call_args[1]["source"] == "room"
    assert call_args[1]["relay"] is True
    assert "Alice" in call_args[0][0]
    assert "Hello room!" in call_args[0][0]

    # relay_meta carries structured info for deferred room_relay in _consumer_loop
    relay_meta = call_args[1]["relay_meta"]
    assert relay_meta["room_name"] == "Room1"
    assert relay_meta["from_name"] == "Alice"
    assert relay_meta["from_id"] == "A"
    assert relay_meta["text"] == "Hello room!"

    # Active agent: both room_chat (chatroom panel) and room_relay (main chat)
    # are sent via the same ws_handler. room_chat+room_relay share ws_handler.
    assert ws_handler._send.call_count == 2
    calls = [c[0][0] for c in ws_handler._send.call_args_list]
    types = {c["type"] for c in calls}
    assert types == {"room_chat", "room_relay"}
    relay_data = [c for c in calls if c["type"] == "room_relay"][0]
    assert relay_data["room_name"] == "Room1"
    assert relay_data["from_name"] == "Alice"
    chat_data = [c for c in calls if c["type"] == "room_chat"][0]
    assert chat_data["room_name"] == "Room1"
    assert chat_data["from_name"] == "Alice"

    # suppress_reply should be True on success
    assert tool.suppress_reply is True
    assert "2" in result  # broadcast to 2 members


@pytest.mark.asyncio
async def test_broadcast_no_room_context():
    """Error when agent not in any room and no room_id given."""
    state = _make_agent_state("A")
    state.controller.agent._current_room_id = ""

    mgr = _make_manager(agents={"A": state})
    tool = BroadcastRoomTool(mgr, "A")
    ctx = ToolContext(cwd="/tmp", messages=[])

    result = await tool.call({"message": "Hello"}, ctx)

    assert "未指定" in result or "不在" in result
    # Error: suppress_reply should be False
    assert tool.suppress_reply is False


@pytest.mark.asyncio
async def test_broadcast_not_in_room():
    """Error when agent is not a member of the specified room."""
    room = _make_room("r1", "Room1", ["B", "C"])
    state_a = _make_agent_state("A")

    mgr = _make_manager(rooms={"r1": room}, agents={"A": state_a})
    tool = BroadcastRoomTool(mgr, "A")
    ctx = ToolContext(cwd="/tmp", messages=[])

    result = await tool.call({"message": "Hello", "room_id": "r1"}, ctx)

    assert "不在" in result
    assert tool.suppress_reply is False


@pytest.mark.asyncio
async def test_broadcast_multi_room_with_room_id_param():
    """Agent in multiple rooms uses room_id to target specific room."""
    room1 = _make_room("r1", "Room1", ["A", "B"])
    room2 = _make_room("r2", "Room2", ["A", "C"])
    state_a = _make_agent_state("A")
    state_b = _make_agent_state("B")
    state_c = _make_agent_state("C")

    main_state = _make_agent_state("1", "Master")
    main_state.controller.handler = MagicMock(_send=AsyncMock())

    mgr = _make_manager(
        rooms={"r1": room1, "r2": room2},
        agents={"A": state_a, "B": state_b, "C": state_c, "1": main_state},
    )

    tool = BroadcastRoomTool(mgr, "A")
    ctx = ToolContext(cwd="/tmp", messages=[])

    result = await tool.call({"message": "To room2", "room_id": "r2"}, ctx)

    # Should enqueue to C (room2 member), not B (room1 only)
    assert state_c.message_queue.enqueue.call_count == 1
    assert state_b.message_queue.enqueue.call_count == 0


# ── suppress_reply in Tool base class ──


def test_tool_base_default_suppress_reply():
    """Tool base class has suppress_reply=False by default."""
    assert Tool.suppress_reply is False


def test_broadcast_tool_suppress_reply_default():
    """BroadcastRoomTool has suppress_reply=True by default."""
    assert BroadcastRoomTool.suppress_reply is True


# ── register_broadcast_tool tests ──


def test_register_broadcast_tool():
    """register_broadcast_tool adds BroadcastRoom to agent's registry."""
    from agentcore.agent_manager import AgentManager
    from agentcore.config import AgentConfig

    # Patch provider creation to avoid API keys
    with patch("agentcore.agent_manager._build_provider") as mock_prov, \
         patch("agentcore.controller._build_provider"):
        mock_prov.return_value = MagicMock(model="test")

        config = AgentConfig(provider="glm")
        mgr = AgentManager(config)

        # Master should not have BroadcastRoom initially
        master = mgr.agents["1"]
        assert master.controller.registry.get("BroadcastRoom") is None

        # Register it
        mgr.register_broadcast_tool("1")

        # Now it should be there
        tool = master.controller.registry.get("BroadcastRoom")
        assert tool is not None
        assert tool.name == "BroadcastRoom"

        # Calling again should not duplicate
        mgr.register_broadcast_tool("1")
        # (registry.register replaces by name, so still just one)


def test_register_broadcast_tool_unknown_agent():
    """register_broadcast_tool silently ignores unknown agent IDs."""
    from agentcore.agent_manager import AgentManager
    from agentcore.config import AgentConfig

    with patch("agentcore.agent_manager._build_provider") as mock_prov, \
         patch("agentcore.controller._build_provider"):
        mock_prov.return_value = MagicMock(model="test")

        config = AgentConfig(provider="glm")
        mgr = AgentManager(config)

        # Should not raise
        mgr.register_broadcast_tool("nonexistent")


# ── agent_message_queue: no auto-broadcast ──


@pytest.mark.asyncio
async def test_message_queue_no_auto_broadcast():
    """Room messages no longer trigger auto-broadcast after agent responds."""
    controller = MagicMock()
    controller._agent_lock = asyncio.Lock()
    controller.send_message = AsyncMock()
    controller.handler = MagicMock()
    controller.handler.on_request = AsyncMock()
    controller.handler.on_enqueued = AsyncMock()

    # Mock agent with manager/rooms attributes
    agent = MagicMock()
    agent._agent_name = "TestAgent"
    agent._agent_id = "agent1"
    agent._agent_manager = None  # No manager = no auto-broadcast path
    agent.messages = [MagicMock(role="assistant", content="response")]
    agent.est_tokens.return_value = 100
    agent._loop_running = True
    controller.agent = agent

    queue = AgentMessageQueue(controller)

    # Enqueue a room message (source="room", relay=False)
    queue.enqueue(
        "[Room: TestRoom | From: User]\nHello",
        source="room",
        room_id="r1",
    )

    await asyncio.sleep(0.2)
    queue.cancel()

    # send_message should have been called (agent processes the message)
    controller.send_message.assert_called_once()

    # But there should be NO additional broadcast — the old auto-broadcast
    # code is removed. If it were still there, it would try to access
    # agent._agent_manager which is None and error/attempt broadcast.
    # We verify simply that send_message was called exactly once.


@pytest.mark.asyncio
async def test_broadcast_room_chat_for_inactive_agent():
    """Non-active agent's BroadcastRoom sends room_chat via mgr.ws_handler."""
    room = _make_room("r1", "Room1", ["A", "B"])
    state_a = _make_agent_state("A", "Alice")
    state_a.controller.agent._current_room_id = "r1"
    state_b = _make_agent_state("B", "Bob")

    # Agent A is NOT the active agent — its handler has no _send
    state_a.controller.handler = MagicMock()
    del state_a.controller.handler._send

    # Global ws_handler has _send (belongs to the active agent)
    ws_handler = MagicMock()
    ws_handler._send = AsyncMock()

    mgr = _make_manager(
        rooms={"r1": room},
        agents={"A": state_a, "B": state_b},
    )
    mgr.ws_handler = ws_handler

    tool = BroadcastRoomTool(mgr, "A")
    ctx = ToolContext(cwd="/tmp", messages=[])

    result = await tool.call({"message": "Hello from inactive!"}, ctx)
    assert "1" in result  # broadcast to 1 member (B only)

    # mgr.ws_handler._send should have been called with room_chat
    ws_handler._send.assert_called_once()
    chat_data = ws_handler._send.call_args[0][0]
    assert chat_data["type"] == "room_chat"
    assert chat_data["room_id"] == "r1"
    assert chat_data["from_id"] == "A"
    assert chat_data["text"] == "Hello from inactive!"

    # room_relay is NOT sent via agent's own handler (no _send)


@pytest.mark.asyncio
async def test_broadcast_blocked_on_send_message_source():
    """BroadcastRoom is blocked when processing a SendMessage private message."""
    room = _make_room("r1", "Room1", ["A", "B"])
    state_a = _make_agent_state("A", "Alice")
    state_a.controller.agent._current_room_id = "r1"
    state_a.controller.agent._current_source = "agent"  # SendMessage triggered
    state_b = _make_agent_state("B", "Bob")

    mgr = _make_manager(
        rooms={"r1": room},
        agents={"A": state_a, "B": state_b},
    )

    tool = BroadcastRoomTool(mgr, "A")
    ctx = ToolContext(cwd="/tmp", messages=[])

    result = await tool.call({"message": "Should be blocked"}, ctx)
    assert "禁止调用" in result
    assert tool.suppress_reply is False
