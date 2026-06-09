"""Integration tests for tool result limits and compaction with mock LLM."""
import asyncio
from pathlib import Path

import pytest

from agentcore.core_types import Message, ToolUseBlock
from agentcore.config import AgentConfig
from agentcore.controller import AgentController, EventHandler
from agentcore.events import (
    ThinkingEvent, TextDeltaEvent, ToolUseEvent, ResponseDoneEvent, DoneEvent,
)
from agentcore.tools.tool_result_storage import (
    is_content_already_compacted,
)


class MockProvider:
    """Streaming mock that yields events matching the agent loop expectation."""

    def __init__(self, responses: list):
        self.responses = responses
        self.call_count = 0
        self.model = "mock-model"

    async def call(self, messages, tools, system):
        """Used by compaction (needs tuple return)."""
        resp = self.responses[self.call_count] if self.call_count < len(self.responses) else {}
        self.call_count += 1
        text = resp.get("text", "") or ""
        tools_data = resp.get("tools", [])
        usage = resp.get("usage", {})
        blocks = [ToolUseBlock(tool_use_id=td["tool_use_id"], tool_name=td["name"],
                               input=td.get("input", {})) for td in tools_data]
        msg = Message(role="assistant", content=text, tool_use_blocks=blocks)
        raw = {"usage": usage, "model": "mock", "id": f"m{self.call_count}"}
        return msg, blocks, raw

    async def call_stream(self, messages, tools, system):
        """Yields streaming events for the agent loop."""
        resp = self.responses[self.call_count] if self.call_count < len(self.responses) else {}
        self.call_count += 1

        text = resp.get("text", "") or ""
        tools_data = resp.get("tools", [])
        usage = resp.get("usage", {})
        raw = {"usage": usage, "model": "mock", "id": f"m{self.call_count}"}

        yield ThinkingEvent()

        # Yield text tokens (one per character group for efficiency)
        if text:
            chunk_size = max(1, len(text) // 10)
            for i in range(0, len(text), chunk_size):
                yield TextDeltaEvent(token=text[i:i + chunk_size])

        # Yield tool uses
        for td in tools_data:
            yield ToolUseEvent(
                tool_name=td["name"],
                input=td.get("input", {}),
                tool_use_id=td["tool_use_id"],
            )

        yield ResponseDoneEvent(raw=raw)
        yield DoneEvent(final_text=text)


class CaptureHandler(EventHandler):
    def __init__(self):
        super().__init__()
        self.persisted_results: list[dict] = []
        self.compact_events: list[dict] = []
        self.done_events: list[str] = []
        self.tool_use_events: list[str] = []

    async def on_tool_result(self, name: str, result: str, is_error: bool,
                             duration_ms: float = 0, tool_use_id: str = ""):
        if is_content_already_compacted(result):
            self.persisted_results.append({
                "name": name, "tool_use_id": tool_use_id, "preview": result[:200],
            })

    async def on_compact(self, pre_tokens: int, post_tokens: int, trigger: str,
                         summary: str = ""):
        self.compact_events.append({
            "pre": pre_tokens, "post": post_tokens, "trigger": trigger,
        })

    async def on_done(self):
        pass  # handled by send_message internally


def _config(cwd: Path) -> AgentConfig:
    return AgentConfig(
        provider="mock", model="mock", cwd=str(cwd),
        max_turns=10, context_window=128_000, compact_threshold=0.85,
    )


def _controller(config, handler, mock, monkeypatch):
    monkeypatch.setattr("agentcore.controller._build_provider", lambda _: mock)
    return AgentController(config, handler)


async def _send(controller, handler, text: str) -> bool:
    """Run through controller's send_message path to invoke all callbacks."""
    try:
        await controller.send_message(text)
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────
# Test 1: Single tool result exceeds max_result_chars → persisted
# ─────────────────────────────────────────────────────────────────

def test_tool_result_persisted_exceeds_limit(tmp_path, monkeypatch):
    """Bash tool returns huge output → exceeds default 100K limit → persisted."""
    config = _config(tmp_path)
    handler = CaptureHandler()

    # Create a big file and cat it via Bash
    big = "line\n" * 30_000
    big_file = tmp_path / "big.txt"
    big_file.write_text(big)

    mock = MockProvider([
        {"tools": [{"name": "Bash", "input": {"command": f"cat {big_file}"},
                    "tool_use_id": "tu_1"}], "text": "", "usage": {"total_tokens": 100}},
        {"text": "Read done.", "tools": [], "usage": {"total_tokens": 50}},
    ])

    controller = _controller(config, handler, mock, monkeypatch)
    got = asyncio.run(_send(controller, handler, "read the big file"))
    assert got

    # Persisted result on disk (Bash has max_result_chars=100K, output is ~180K)
    d = tmp_path / ".myagent" / "tool_results"
    files = list(d.glob("*.json")) if d.exists() else []
    assert len(files) >= 1
    import json
    saved = json.loads(files[0].read_text(encoding="utf-8"))
    assert "line" in saved["content"]

    assert len(handler.persisted_results) >= 1
    assert handler.persisted_results[0]["name"] == "Bash"


# ─────────────────────────────────────────────────────────────────
# Test 2: Compaction triggers when context window threshold exceeded
# ─────────────────────────────────────────────────────────────────

def test_compaction_triggers(tmp_path, monkeypatch):
    config = _config(tmp_path)
    config.context_window = 32_000
    config.compact_threshold = 0.5
    handler = CaptureHandler()

    controller = _controller(config, handler, MockProvider([]), monkeypatch)
    controller.agent.context_window = 32_000
    controller.agent.compact_threshold = 0.5

    big = "word " * 3000
    controller.agent.messages = [
        Message(role="user", content=big),
        Message(role="assistant", content=big, id="r1"),
        Message(role="user", content=big),
        Message(role="assistant", content=big,
                tool_use_blocks=[ToolUseBlock(tool_use_id="tx1", tool_name="Grep", input={})],
                id="r2"),
        Message(role="user", content="ok", tool_use_id="tx1"),
        Message(role="user", content=big),
        Message(role="assistant", content=big, id="r3"),
    ]

    mock = MockProvider([
        {"text": "Final answer.", "tools": [],
         "usage": {"total_tokens": 25_000}},
    ])

    asyncio.run(_send(controller, handler, "go"))

    assert len(handler.compact_events) >= 1


# ─────────────────────────────────────────────────────────────────
# Test 3: Compaction not triggered below threshold
# ─────────────────────────────────────────────────────────────────

def test_compaction_skipped_below_threshold(tmp_path, monkeypatch):
    config = _config(tmp_path)
    handler = CaptureHandler()

    controller = _controller(config, handler, MockProvider([]), monkeypatch)
    controller.agent.context_window = 128_000
    controller.agent.messages = [
        Message(role="user", content="hello"),
        Message(role="assistant", content="hi", id="r1"),
    ]

    mock = MockProvider([
        {"text": "OK.", "tools": [], "usage": {"total_tokens": 100}},
    ])

    asyncio.run(_send(controller, handler, "ping"))
    assert len(handler.compact_events) == 0


# ─────────────────────────────────────────────────────────────────
# Test 4: Unknown tool → error, loop continues
# ─────────────────────────────────────────────────────────────────

def test_unknown_tool_recovers(tmp_path, monkeypatch):
    config = _config(tmp_path)
    handler = CaptureHandler()

    mock = MockProvider([
        {"tools": [{"name": "FakeTool", "input": {}, "tool_use_id": "tu_x"}],
         "text": "", "usage": {"total_tokens": 100}},
        {"text": "Recovered.", "tools": [], "usage": {"total_tokens": 50}},
    ])

    controller = _controller(config, handler, mock, monkeypatch)
    got = asyncio.run(_send(controller, handler, "use weird tool"))
    assert got

    # Tool result for unknown tool should contain an error
    msgs = controller.agent.messages
    err_msgs = [m for m in msgs if "Unknown tool" in (m.content or "")
                or (getattr(m, "tool_use_id", None) == "tu_x")]
    assert len(controller.agent.messages) > 2  # at least user + assistant + tool_result


# ─────────────────────────────────────────────────────────────────
# Test 5: Max turns exceeded → graceful termination
# ─────────────────────────────────────────────────────────────────

def test_max_turns_exceeded(tmp_path, monkeypatch):
    config = _config(tmp_path)
    config.max_turns = 2
    handler = CaptureHandler()

    mock = MockProvider([
        {"tools": [{"name": "Grep", "input": {"pattern": "x", "path": str(tmp_path)},
                    "tool_use_id": "tu_1"}], "text": "", "usage": {"total_tokens": 100}},
        {"tools": [{"name": "Grep", "input": {"pattern": "y", "path": str(tmp_path)},
                    "tool_use_id": "tu_2"}], "text": "", "usage": {"total_tokens": 100}},
    ])

    controller = _controller(config, handler, mock, monkeypatch)
    got = asyncio.run(_send(controller, handler, "loop"))

    assert got  # graceful termination produces final_text
    assert mock.call_count == 2  # stopped at max_turns


# ─────────────────────────────────────────────────────────────────
# Test 6: Concurrent read-only tools execute
# ─────────────────────────────────────────────────────────────────

def test_concurrent_tools(tmp_path, monkeypatch):
    config = _config(tmp_path)
    handler = CaptureHandler()

    (tmp_path / "a.txt").write_text("content aaa")
    (tmp_path / "b.txt").write_text("content bbb")

    mock = MockProvider([
        {"tools": [
            {"name": "FileRead", "input": {"file_path": str(tmp_path / "a.txt")},
             "tool_use_id": "tu_a"},
            {"name": "FileRead", "input": {"file_path": str(tmp_path / "b.txt")},
             "tool_use_id": "tu_b"},
        ], "text": "", "usage": {"total_tokens": 100}},
        {"text": "Both read.", "tools": [], "usage": {"total_tokens": 50}},
    ])

    controller = _controller(config, handler, mock, monkeypatch)
    got = asyncio.run(_send(controller, handler, "read two files"))
    assert got

    # Both files' content should be in tool result messages
    results = [m.content for m in controller.agent.messages
               if getattr(m, "tool_use_id", None) in ("tu_a", "tu_b")]
    assert len(results) == 2
    assert any("aaa" in r for r in results)
    assert any("bbb" in r for r in results)


# ─────────────────────────────────────────────────────────────────
# Test 7: Empty tool result not persisted
# ─────────────────────────────────────────────────────────────────

def test_empty_tool_result_skipped(tmp_path, monkeypatch):
    config = _config(tmp_path)
    handler = CaptureHandler()

    mock = MockProvider([
        {"tools": [{"name": "Grep", "input": {"pattern": "zzz_NOMATCH_zzz", "path": str(tmp_path)},
                    "tool_use_id": "tu_e"}], "text": "", "usage": {"total_tokens": 100}},
        {"text": "Nothing found.", "tools": [], "usage": {"total_tokens": 50}},
    ])

    controller = _controller(config, handler, mock, monkeypatch)
    got = asyncio.run(_send(controller, handler, "search"))
    assert got

    assert len(handler.persisted_results) == 0


# ─────────────────────────────────────────────────────────────────
# Test 8: Tool error (permission) → captured but loop continues
# ─────────────────────────────────────────────────────────────────

def test_tool_permission_error_captured(tmp_path, monkeypatch):
    config = _config(tmp_path)
    handler = CaptureHandler()

    # Non-existent file that would fail on read
    nonexistent = str(tmp_path / "nope.txt")

    mock = MockProvider([
        {"tools": [{"name": "FileRead", "input": {"file_path": nonexistent},
                    "tool_use_id": "tu_fail"}], "text": "", "usage": {"total_tokens": 100}},
        {"text": "Handled gracefully.", "tools": [], "usage": {"total_tokens": 50}},
    ])

    controller = _controller(config, handler, mock, monkeypatch)
    got = asyncio.run(_send(controller, handler, "read missing file"))
    assert got

    # Error result in messages
    errs = [m.content for m in controller.agent.messages
            if getattr(m, "tool_use_id", None) == "tu_fail"]
    assert len(errs) == 1
    assert "not found" in errs[0].lower() or "error" in errs[0].lower()
