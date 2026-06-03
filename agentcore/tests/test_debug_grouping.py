"""Tests for WsEventHandler._compute_group_idx persistent G-number mapping."""
from unittest.mock import MagicMock
from agentcore.core_types import Message
from agentcore.ws_server import WsEventHandler


def _make_handler(messages: list[Message] | None = None):
    """Create a minimal WsEventHandler for testing _compute_group_idx."""
    controller = MagicMock()
    controller.agent = MagicMock()
    controller.agent.messages = messages or []
    ws = MagicMock()
    ws.send = MagicMock()
    handler = WsEventHandler(ws, controller)
    # Manually seed _debug_entries (simulating previously sent events)
    handler._debug_entries = []
    return handler


def _add_entry(handler: WsEventHandler, group_key: str | None, group_idx: int | None,
               opacity: float = 1.0):
    """Simulate a previously sent debug entry in _debug_entries."""
    handler._debug_entries.append({
        "prefix": "X",
        "message": "X",
        "color": "#000",
        "group_key": group_key,
        "group_idx": group_idx,
        "opacity": opacity,
    })


class TestGroupIdxBasic:
    """Test G-number assignment for a simple request-response flow."""

    def test_first_request_is_g0(self):
        h = _make_handler([])
        assert h._compute_group_idx("user") == 0

    def test_first_response_is_g1(self):
        h = _make_handler([
            Message(role="user", content="hello"),
            Message(role="assistant", content="hi", id="msg_001"),
        ])
        _add_entry(h, "user", 0)  # the [Request] that came before
        assert h._compute_group_idx("asst:msg_001") == 1

    def test_second_request_is_g2(self):
        h = _make_handler([
            Message(role="user", content="hello"),
            Message(role="assistant", content="hi", id="msg_001"),
        ])
        _add_entry(h, "user", 0)
        _add_entry(h, "asst:msg_001", 1)
        assert h._compute_group_idx("user") == 2

    def test_response_with_tools(self):
        """[Response] with tool_use gets the next G after the request."""
        h = _make_handler([
            Message(role="user", content="hello"),
            Message(role="assistant", content="hi", id="msg_001"),
            Message(role="user", content="edit file"),
            Message(role="assistant", content="", tool_use_blocks=[
                MagicMock(tool_use_id="tu_001", tool_name="Read", input={}),
            ], id="msg_002"),
        ])
        _add_entry(h, "user", 0)
        _add_entry(h, "asst:msg_001", 1)
        _add_entry(h, "user", 2)
        assert h._compute_group_idx("asst:msg_002") == 3

    def test_tool_result_same_group_as_response(self):
        """[Tool] entries share the same G as their parent [Response]."""
        from agentcore.core_types import ToolUseBlock
        h = _make_handler([
            Message(role="user", content="hello"),
            Message(role="assistant", content="hi", id="msg_001"),
            Message(role="user", content="edit"),
            Message(role="assistant", content="", tool_use_blocks=[
                ToolUseBlock(tool_use_id="tu_001", tool_name="Read", input={}),
            ], id="msg_002"),
            Message(role="user", content="file content", tool_use_id="tu_001"),
        ])
        _add_entry(h, "user", 0)
        _add_entry(h, "asst:msg_001", 1)
        _add_entry(h, "user", 2)
        _add_entry(h, "asst:msg_002", 3)
        # tool entry uses tool_use_id key
        assert h._compute_group_idx("tool:tu_001") == 3

    def test_tool_in_tool_use_blocks_no_result_yet(self):
        """Tool key lookup via assistant's tool_use_blocks when result not yet in messages."""
        from agentcore.core_types import ToolUseBlock
        h = _make_handler([
            Message(role="user", content="hello"),
            Message(role="assistant", content="hi", id="msg_001"),
            Message(role="user", content="edit"),
            Message(role="assistant", content="", tool_use_blocks=[
                ToolUseBlock(tool_use_id="tu_001", tool_name="Read", input={}),
            ], id="msg_002"),
        ])
        _add_entry(h, "user", 0)
        _add_entry(h, "asst:msg_001", 1)
        _add_entry(h, "user", 2)
        _add_entry(h, "asst:msg_002", 3)
        # Tool result not in messages yet, but tool_use_blocks has the ID
        assert h._compute_group_idx("tool:tu_001") == 3

    def test_final_response_after_tools(self):
        """[Final Response] after tools gets its own new G."""
        from agentcore.core_types import ToolUseBlock
        h = _make_handler([
            Message(role="user", content="hello"),
            Message(role="assistant", content="hi", id="msg_001"),
            Message(role="user", content="edit"),
            Message(role="assistant", content="", tool_use_blocks=[
                ToolUseBlock(tool_use_id="tu_001", tool_name="Read", input={}),
            ], id="msg_002"),
            Message(role="user", content="done", tool_use_id="tu_001"),
            Message(role="assistant", content="ok done", id="msg_003"),
        ])
        _add_entry(h, "user", 0)
        _add_entry(h, "asst:msg_001", 1)
        _add_entry(h, "user", 2)
        _add_entry(h, "asst:msg_002", 3)
        _add_entry(h, "tool:tu_001", 3)
        assert h._compute_group_idx("asst:msg_003") == 4


class TestGroupIdxPersistence:
    """Test G-number persistence after compact/snip."""

    def test_surviving_entries_keep_gid(self):
        """After compact removes old messages, surviving entries keep their G number."""
        from agentcore.core_types import ToolUseBlock
        # Simulate: 3 rounds happened, then compact removed rounds 0-1
        # Remaining messages: [compact_msg, request2, response2]
        h = _make_handler([
            Message(role="user", content="[Context compressed] ..."),
            Message(role="user", content="req2"),
            Message(role="assistant", content="resp2", id="msg_002"),
        ])
        # Old entries: G0,G1 are grayed out, G2,G3 survived
        _add_entry(h, "user", 0, opacity=0.4)
        _add_entry(h, "asst:msg_001", 1, opacity=0.4)
        _add_entry(h, "user", 2, opacity=1.0)
        _add_entry(h, "asst:msg_002", 3, opacity=1.0)
        # A new request should NOT reuse G0 or G1 (they're grayed but still exist)
        # max_persistent among non-grayed = 3, next_gid = 4
        assert h._compute_group_idx("user") == 4

    def test_null_group_key_returns_null(self):
        h = _make_handler([])
        assert h._compute_group_idx(None) is None
