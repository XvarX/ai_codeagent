# tests/test_session_manager.py
"""Unit tests for SessionManager — concurrent session lifecycle management."""

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentcore.config import AgentConfig
from agentcore.session_manager import SessionManager, SessionSlot


# ── Helpers ────────────────────────────────────────────────

def _make_config() -> AgentConfig:
    return AgentConfig(provider="openai", model="test-model", cwd="/tmp/test")


def _make_manager() -> SessionManager:
    config = _make_config()
    store = MagicMock()
    dd = MagicMock()
    ws = MagicMock()
    return SessionManager(config, store, dd, ws)


def _mock_agent_manager():
    """Build a mocked AgentManager with an initial agent slot."""
    mgr = MagicMock()

    # AgentState-like mock for initial agent (id=1)
    initial_state = MagicMock()
    initial_state.status = "running"
    initial_state.controller = MagicMock()
    initial_state.controller.connect_mcp = AsyncMock()
    initial_state.controller.cancel = AsyncMock()
    initial_state.controller.agent = MagicMock()
    initial_state.controller.agent.bind_session = MagicMock()
    initial_state.controller.agent.restore_messages = MagicMock()
    initial_state.controller.agent.messages = []

    mgr.agents = {"1": initial_state}
    mgr.ws_handler = None
    mgr.on_change = None

    # kill and cancel are async
    mgr.kill = AsyncMock()
    return mgr


# ── Tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_session():
    """create_session builds a SessionSlot and sets it as active."""
    sm = _make_manager()

    with patch("agentcore.session_manager.AgentManager") as MockMgr, \
         patch("agentcore.ws_server.WsEventHandler") as MockHandler, \
         patch("agentcore.agent_definitions.load_user_agents", return_value={}):

        mock_mgr = _mock_agent_manager()
        MockMgr.return_value = mock_mgr

        mock_handler = MagicMock()
        MockHandler.return_value = mock_handler

        sid = await sm.create_session("/tmp/proj", "sess-1", title="Test")

        assert sid == "sess-1"
        assert sm.active_session_id == "sess-1"
        assert "sess-1" in sm.slots

        slot = sm.slots["sess-1"]
        assert isinstance(slot, SessionSlot)
        assert slot.session_id == "sess-1"
        assert slot.project_path == "/tmp/proj"

        # Verify MCP connect was awaited
        mock_mgr.agents["1"].controller.connect_mcp.assert_awaited_once()

        # Verify bind_session was called
        initial_agent = mock_mgr.agents["1"].controller.agent
        initial_agent.bind_session.assert_called_once_with(
            sm._store, "/tmp/proj", "sess-1", agent_id="1")

        # Verify messages were cleared
        assert initial_agent.messages == []


@pytest.mark.asyncio
async def test_load_session():
    """load_session restores messages and debug entries from store."""
    sm = _make_manager()
    sm._store.load_messages.return_value = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
    ]
    sm._store.load_debug_log.return_value = [
        {"type": "Request", "message": "test"},
    ]

    with patch("agentcore.session_manager.AgentManager") as MockMgr, \
         patch("agentcore.ws_server.WsEventHandler") as MockHandler, \
         patch("agentcore.agent_definitions.load_user_agents", return_value={}):

        mock_mgr = _mock_agent_manager()
        MockMgr.return_value = mock_mgr

        mock_handler = MagicMock()
        MockHandler.return_value = mock_handler

        await sm.load_session("/tmp/proj", "sess-load")

        assert sm.active_session_id == "sess-load"
        assert "sess-load" in sm.slots

        slot = sm.slots["sess-load"]
        assert slot.session_id == "sess-load"

        # Verify store.load_messages was called
        sm._store.load_messages.assert_called_once_with("/tmp/proj", "sess-load")

        # Verify restore_messages was called with loaded messages
        initial_agent = mock_mgr.agents["1"].controller.agent
        initial_agent.restore_messages.assert_called_once_with(
            [{"role": "user", "content": "Hello"},
             {"role": "assistant", "content": "Hi"}])

        # Verify debug entries were restored on handler
        assert len(mock_handler._debug_entries) == 1
        assert mock_handler._debug_entries[0]["type"] == "Request"


def test_switch_session():
    """switch_session changes active session, returns False for unknown."""
    sm = _make_manager()

    # Manually populate slots
    sm.slots["sess-a"] = MagicMock(spec=SessionSlot)
    sm.slots["sess-b"] = MagicMock(spec=SessionSlot)

    # Switch to existing
    assert sm.switch_session("sess-b") is True
    assert sm.active_session_id == "sess-b"

    # Switch to another
    assert sm.switch_session("sess-a") is True
    assert sm.active_session_id == "sess-a"

    # Switch to unknown
    assert sm.switch_session("sess-unknown") is False
    assert sm.active_session_id == "sess-a"  # unchanged


@pytest.mark.asyncio
async def test_destroy_session():
    """destroy_session kills agents, removes slot, clears active if needed."""
    sm = _make_manager()

    mock_mgr = _mock_agent_manager()
    mock_mgr.agents["worker-1"] = MagicMock()
    mock_mgr.agents["worker-1"].controller = MagicMock()

    slot = MagicMock(spec=SessionSlot)
    slot.agent_manager = mock_mgr

    sm.slots["sess-die"] = slot
    sm.active_session_id = "sess-die"

    await sm.destroy_session("sess-die")

    # Slot should be removed
    assert "sess-die" not in sm.slots

    # Active should be cleared
    assert sm.active_session_id == ""

    # Non-initial agents should be killed
    mock_mgr.kill.assert_any_call("worker-1")

    # Initial agent controller should be cancelled
    mock_mgr.agents["1"].controller.cancel.assert_awaited_once()

    # Destroying non-existent session is a no-op
    await sm.destroy_session("no-such-session")


def test_get_active():
    """get_active returns the currently active slot."""
    sm = _make_manager()

    slot_a = MagicMock(spec=SessionSlot)
    sm.slots["sess-a"] = slot_a
    sm.active_session_id = "sess-a"

    assert sm.get_active() is slot_a

    # Switch and verify
    slot_b = MagicMock(spec=SessionSlot)
    sm.slots["sess-b"] = slot_b
    sm.active_session_id = "sess-b"

    assert sm.get_active() is slot_b


def test_get_active_empty():
    """get_active returns None when no active session."""
    sm = _make_manager()
    assert sm.active_session_id == ""
    assert sm.get_active() is None
