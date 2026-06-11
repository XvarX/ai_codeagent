"""Unit tests for Agent._persist_message and Agent._persist_llm_log."""

import json
import tempfile
from pathlib import Path

import pytest

from agentcore.agent import Agent
from agentcore.core_types import Message, ToolUseBlock
from agentcore.data_dir import DataDir
from agentcore.session_store import SessionStore
from agentcore.tools.registry import ToolRegistry


# ── Helpers ──────────────────────────────────────────────────────────────


class MockProvider:
    """Minimal mock provider — just enough to instantiate Agent."""

    model = "test-model"

    async def call(self, *a, **kw):
        pass

    async def call_stream(self, *a, **kw):
        return
        yield  # make it an async generator


def _make_agent_with_store(tmp_path: Path) -> tuple[Agent, SessionStore, str, str]:
    """Create an Agent backed by a real SessionStore under tmp_path."""
    dd = DataDir(tmp_path / ".ai-code-agent")
    dd.init()
    store = SessionStore(dd)

    project_path = str(tmp_path / "fake-project")
    store.register_project(project_path, name="test-project")
    session_id = store.create_session(project_path, title="persistence-test")

    agent = Agent(
        provider=MockProvider(),
        registry=ToolRegistry(),
        cwd=str(tmp_path),
        session_store=store,
        session_project=project_path,
        session_id=session_id,
    )
    return agent, store, project_path, session_id


def _make_agent_without_store(tmp_path: Path) -> Agent:
    """Create an Agent with no session_store (persistence disabled)."""
    return Agent(
        provider=MockProvider(),
        registry=ToolRegistry(),
        cwd=str(tmp_path),
    )


# ── Tests ────────────────────────────────────────────────────────────────


class TestPersistMessage:
    """Tests for Agent._persist_message."""

    def test_persist_user_message(self, tmp_path):
        """A user message is serialized and appended to the session store."""
        agent, store, project, sid = _make_agent_with_store(tmp_path)

        msg = Message(role="user", content="Hello, world!")
        agent._persist_message(msg)

        stored = store.load_messages(project, sid)
        assert len(stored) == 1
        assert stored[0]["role"] == "user"
        assert stored[0]["content"] == "Hello, world!"
        assert "tool_use_blocks" not in stored[0]
        assert "tool_use_id" not in stored[0]

    def test_persist_assistant_message(self, tmp_path):
        """An assistant message is serialized and appended to the session store."""
        agent, store, project, sid = _make_agent_with_store(tmp_path)

        msg = Message(role="assistant", content="Hi there!")
        agent._persist_message(msg)

        stored = store.load_messages(project, sid)
        assert len(stored) == 1
        assert stored[0]["role"] == "assistant"
        assert stored[0]["content"] == "Hi there!"

    def test_persist_message_with_tool_use_blocks(self, tmp_path):
        """Tool use blocks are serialized as a list of dicts in the stored message."""
        agent, store, project, sid = _make_agent_with_store(tmp_path)

        blocks = [
            ToolUseBlock(tool_use_id="tu_001", tool_name="Bash", input={"command": "ls"}),
            ToolUseBlock(tool_use_id="tu_002", tool_name="FileRead", input={"path": "/tmp/x"}),
        ]
        msg = Message(role="assistant", content="", tool_use_blocks=blocks)
        agent._persist_message(msg)

        stored = store.load_messages(project, sid)
        assert len(stored) == 1
        serialized_blocks = stored[0]["tool_use_blocks"]
        assert len(serialized_blocks) == 2
        assert serialized_blocks[0] == {
            "tool_use_id": "tu_001",
            "tool_name": "Bash",
            "input": {"command": "ls"},
        }
        assert serialized_blocks[1] == {
            "tool_use_id": "tu_002",
            "tool_name": "FileRead",
            "input": {"path": "/tmp/x"},
        }

    def test_persist_message_with_tool_result(self, tmp_path):
        """A tool-result message (tool_use_id set) is serialized correctly."""
        agent, store, project, sid = _make_agent_with_store(tmp_path)

        msg = Message(
            role="user",
            content="file contents here",
            tool_use_id="tu_001",
        )
        agent._persist_message(msg)

        stored = store.load_messages(project, sid)
        assert len(stored) == 1
        assert stored[0]["tool_use_id"] == "tu_001"
        assert stored[0]["content"] == "file contents here"
        # No tool_use_blocks key since the list is empty
        assert "tool_use_blocks" not in stored[0]

    def test_persist_llm_log(self, tmp_path):
        """_persist_llm_log writes a dict entry into the session's llm_log.json."""
        agent, store, project, sid = _make_agent_with_store(tmp_path)

        log_entry = {
            "id": "resp_abc123",
            "model": "test-model",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        agent._persist_llm_log(log_entry)

        # Read the raw file via DataDir (per-agent path)
        dd = store._dd
        log_path = dd.agent_dir(project, sid, "1") / "llm_log.json"
        assert log_path.exists()
        logs = json.loads(log_path.read_text(encoding="utf-8"))
        assert len(logs) == 1
        assert logs[0]["id"] == "resp_abc123"
        assert logs[0]["usage"]["input_tokens"] == 10

    def test_no_persist_without_store(self, tmp_path):
        """_persist_message is a no-op when session_store is None — no errors."""
        agent = _make_agent_without_store(tmp_path)
        # These should not raise
        agent._persist_message(Message(role="user", content="nothing"))
        agent._persist_message(Message(role="assistant", content="happens"))
        # _persist_llm_log is also a no-op
        agent._persist_llm_log({"some": "data"})
        # Verify in-memory messages are untouched (method doesn't modify them)
        assert len(agent.messages) == 0

    def test_no_persist_without_session_id(self, tmp_path):
        """_persist_message is a no-op when session_store is set but session_id is None."""
        dd = DataDir(tmp_path / ".ai-code-agent")
        dd.init()
        store = SessionStore(dd)

        agent = Agent(
            provider=MockProvider(),
            registry=ToolRegistry(),
            cwd=str(tmp_path),
            session_store=store,
            session_project="/fake",
            session_id=None,  # no session id
        )
        # Should not raise or write anything
        agent._persist_message(Message(role="user", content="orphan"))
        agent._persist_llm_log({"orphan": True})
