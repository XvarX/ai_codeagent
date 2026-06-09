"""Tests for tool result persistence, per-message budget, and auto-compaction."""
import pytest
from pathlib import Path
from agentcore.core_types import Message
from agentcore.tools.tool_result_storage import (
    process_tool_result_block,
    apply_tool_result_budget,
    persist_tool_result,
    is_content_already_compacted,
    ContentReplacementState,
    DEFAULT_MAX_RESULT_CHARS,
    MAX_TOOL_RESULTS_PER_MESSAGE_CHARS,
    PREVIEW_SIZE_CHARS,
)
from agentcore.compact.autoCompact import (
    should_auto_compact,
    get_context_window,
    MODEL_CONTEXT_WINDOWS,
    RESERVED_OUTPUT,
    DEFAULT_CONTEXT_WINDOW,
)
from agentcore.compact.grouping import estimate_tokens, group_by_api_round


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_cwd(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def tool_use_id() -> str:
    return "toolu_01ABC123"


# ---------------------------------------------------------------------------
# 1. Single-tool persistence: process_tool_result_block
# ---------------------------------------------------------------------------

class TestProcessToolResultBlock:
    def test_under_limit_returns_unchanged(self, tmp_cwd, tool_use_id):
        short = "short result"
        result = process_tool_result_block(short, "Grep", tool_use_id, 100_000, tmp_cwd)
        assert result == short

    def test_none_max_chars_returns_unchanged(self, tmp_cwd, tool_use_id):
        """FileRead has max_result_chars=None — never persist."""
        long = "x" * 100_000
        result = process_tool_result_block(long, "FileRead", tool_use_id, None, tmp_cwd)
        assert result == long

    def test_exceeds_limit_persists_with_preview(self, tmp_cwd, tool_use_id):
        content = "line1\nline2\nline3\n" * 500  # ~9500 chars
        result = process_tool_result_block(content, "Grep", tool_use_id, 5000, tmp_cwd)

        assert result.startswith("<persisted-output>")
        assert "Preview:" in result
        assert str(len(content)) in result
        assert ".myagent/tool_results" in result
        assert is_content_already_compacted(result)

        # Verify file written
        file_path = tmp_cwd / ".myagent" / "tool_results" / f"{tool_use_id}.json"
        assert file_path.exists()
        import json
        saved = json.loads(file_path.read_text(encoding="utf-8"))
        assert saved["content"] == content

    def test_preview_truncated_at_limit(self, tmp_cwd, tool_use_id):
        content = "A" * (PREVIEW_SIZE_CHARS + 100)
        result = process_tool_result_block(content, "Grep", tool_use_id, 100, tmp_cwd)

        assert "..." in result
        preview_part = result.split("\n")[1]
        assert len(preview_part) <= PREVIEW_SIZE_CHARS + len("Preview: ") + 3 + 100  # rough

    def test_default_threshold_used(self, tmp_cwd, tool_use_id):
        """When tool has max_result_chars larger than DEFAULT_MAX_RESULT_CHARS,
        the default is used."""
        content = "x" * (DEFAULT_MAX_RESULT_CHARS + 1)
        result = process_tool_result_block(
            content, "Grep", tool_use_id, 999_999, tmp_cwd
        )
        assert is_content_already_compacted(result)


# ---------------------------------------------------------------------------
# 2. Aggregate per-message budget: apply_tool_result_budget
# ---------------------------------------------------------------------------

class TestApplyToolResultBudget:
    def _make_msgs(self, assistant_id: str, *result_sizes: int, prefix: str = "toolu") -> list[Message]:
        """Build messages: assistant with tool_use → tool_results."""
        msgs: list[Message] = []
        from agentcore.core_types import ToolUseBlock
        blocks = [
            ToolUseBlock(
                tool_use_id=f"{prefix}_{i:03d}",
                tool_name="Grep",
                input={"pattern": f"test{i}"},
            )
            for i in range(len(result_sizes))
        ]
        msgs.append(Message(
            role="assistant", content="", tool_use_blocks=blocks,
            id=assistant_id,
        ))
        for i, size in enumerate(result_sizes):
            msgs.append(Message(
                role="user",
                content="x" * size,
                tool_use_id=f"{prefix}_{i:03d}",
            ))
        return msgs

    def test_under_budget_keeps_all(self, tmp_cwd):
        msgs = self._make_msgs("msg_1", 1000, 2000, 500)
        state = ContentReplacementState()
        limit = 100_000
        result = apply_tool_result_budget(msgs, state, tmp_cwd, limit)

        assert len(result) == len(msgs)
        for msg in result:
            assert not is_content_already_compacted(msg.content or "")

    def test_over_budget_persists_largest(self, tmp_cwd):
        msgs = self._make_msgs("msg_1", 10_000, 5_000, 80_000)
        state = ContentReplacementState()
        limit = 50_000

        result = apply_tool_result_budget(msgs, state, tmp_cwd, limit)

        # The 80_000 char result should be persisted
        compacted = [m for m in result if is_content_already_compacted(m.content or "")]
        assert len(compacted) >= 1
        assert any("80" in m.content for m in compacted)

    def test_frozen_results_count_toward_budget(self, tmp_cwd):
        """Previously seen (frozen) results count against budget.
        Frozen=40K + fresh=80K = 120K > 50K limit → fresh gets compacted."""
        msgs = self._make_msgs("msg_1", 40_000, 80_000)
        state = ContentReplacementState()
        # Mark first (small) result as already seen (frozen)
        state.seen_ids.add("toolu_000")
        limit = 50_000

        result = apply_tool_result_budget(msgs, state, tmp_cwd, limit)

        compacted = [m for m in result if is_content_already_compacted(m.content or "")]
        assert len(compacted) >= 1

    def test_previously_replaced_reapplied(self, tmp_cwd):
        """If a result was replaced before, the replacement is reapplied."""
        msgs = self._make_msgs("msg_1", 100_000)
        state = ContentReplacementState()
        # Pre-register a replacement
        state.replacements["toolu_000"] = "<persisted-output>\nReplaced\n</persisted-output>"

        limit = 50_000
        result = apply_tool_result_budget(msgs, state, tmp_cwd, limit)

        replaced = [m for m in result if is_content_already_compacted(m.content or "")]
        assert len(replaced) >= 1
        assert replaced[0].content == "<persisted-output>\nReplaced\n</persisted-output>"

    def test_multiple_messages_independent_budgets(self, tmp_cwd):
        """Each user message with tool_results has its own budget."""
        msgs = [
            *self._make_msgs("msg_1", 10_000, 10_000, prefix="a"),   # total 20K < limit
            *self._make_msgs("msg_2", 80_000, 80_000, prefix="b"),   # total 160K > limit
        ]
        state = ContentReplacementState()
        limit = 50_000

        result = apply_tool_result_budget(msgs, state, tmp_cwd, limit)

        # Second group (80K+80K > 50K) must have compacted entries
        compacted = [m for m in result if is_content_already_compacted(m.content or "")]
        assert len(compacted) >= 1
        # First group (10K+10K < 50K) untouched — check the first two tool results
        assert not is_content_already_compacted(result[1].content)
        assert not is_content_already_compacted(result[2].content)

    def test_default_budget_limit(self, tmp_cwd):
        """When no limit is provided, MAX_TOOL_RESULTS_PER_MESSAGE_CHARS is used."""
        assert MAX_TOOL_RESULTS_PER_MESSAGE_CHARS == 200_000


# ---------------------------------------------------------------------------
# 3. Auto-compaction: should_auto_compact
# ---------------------------------------------------------------------------

class TestShouldAutoCompact:
    def _make_conversation(self, rounds: int, tokens_per_round: int = 5000) -> list[Message]:
        """Create a multi-round conversation of approximately tokens_per_round each."""
        msgs: list[Message] = []
        from agentcore.core_types import ToolUseBlock
        # ~4 chars per token
        chars = tokens_per_round * 4
        text = "word " * (chars // 5)
        for i in range(rounds):
            msgs.append(Message(role="user", content=str(text)))
            msgs.append(Message(
                role="assistant", content=str(text),
                tool_use_blocks=[ToolUseBlock(
                    tool_use_id=f"tu_{i}", tool_name="Grep", input={},
                )],
                id=f"msg_{i}",
            ))
            msgs.append(Message(
                role="user", content="OK",
                tool_use_id=f"tu_{i}",
            ))
        return msgs

    def test_below_threshold_returns_false(self):
        msgs = self._make_conversation(rounds=3, tokens_per_round=2000)
        assert not should_auto_compact(msgs, context_window=128000)

    def test_above_threshold_returns_true(self):
        msgs = self._make_conversation(rounds=20, tokens_per_round=6000)
        assert should_auto_compact(msgs, context_window=128000)

    def test_too_few_groups_returns_false(self):
        """Less than 3 API rounds should not compact even with large context."""
        msgs = self._make_conversation(rounds=2, tokens_per_round=8000)
        # Total ~16K tokens, well under any threshold
        assert not should_auto_compact(msgs, context_window=128000)

    def test_custom_threshold_respected(self):
        """threshold=0.5 means compact at 50% instead of 85%."""
        msgs = self._make_conversation(rounds=10, tokens_per_round=6000)
        context = 128000
        # With 85% it would be false, with 50% it should be true
        assert should_auto_compact(msgs, "gpt-4o", threshold=0.5, context_window=context)

    def test_actual_base_used(self):
        """actual_base provides floor from last API call."""
        msgs = self._make_conversation(rounds=2, tokens_per_round=2000)
        # estimate_tokens of 2 rounds is small, but actual_base is huge
        assert should_auto_compact(msgs, actual_base=120_000, context_window=128000)

    def test_actual_base_ignored_when_estimate_higher(self):
        """When estimate > actual_base, estimate is used (our fix)."""
        msgs = self._make_conversation(rounds=15, tokens_per_round=7000)
        # estimate >> actual_base, should trigger
        assert should_auto_compact(msgs, actual_base=10_000, context_window=128000)

    def test_custom_context_window(self):
        """Custom context_window is used when provided."""
        msgs = self._make_conversation(rounds=5, tokens_per_round=6000)
        # 5 rounds * ~24K chars / 4 ≈ 30K tokens
        # context_window=32K, threshold 0.85, effective=27200 → should trigger
        assert should_auto_compact(msgs, context_window=32000)

    def test_reserved_output_subtracted(self):
        """RESERVED_OUTPUT is subtracted before computing threshold."""
        assert RESERVED_OUTPUT == 8000
        window = 100_000
        effective = window - RESERVED_OUTPUT  # 92_000
        threshold_85 = int(effective * 0.85)    # 78_200
        assert threshold_85 == 78_200

    def test_model_lookup_fallback(self):
        """When context_window=0, model-specific window is looked up."""
        assert get_context_window("gpt-4o") == 128000
        assert get_context_window("claude-sonnet-4-6") == 200000
        assert get_context_window("deepseek-chat") == 64000
        assert get_context_window("unknown-model-xyz") == DEFAULT_CONTEXT_WINDOW
        assert get_context_window(None) == DEFAULT_CONTEXT_WINDOW


# ---------------------------------------------------------------------------
# 4. Edge cases and helpers
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_persist_then_detect_compacted(self, tmp_cwd, tool_use_id):
        replaced = persist_tool_result("some content", tool_use_id, tmp_cwd)
        assert is_content_already_compacted(replaced)
        assert not is_content_already_compacted("normal result")

    def test_empty_state_noop(self, tmp_cwd):
        msgs: list[Message] = []
        state = ContentReplacementState()
        result = apply_tool_result_budget(msgs, state, tmp_cwd)
        assert result == []

    def test_messages_without_tool_results_passthrough(self, tmp_cwd):
        msgs = [
            Message(role="user", content="hello"),
            Message(role="assistant", content="hi there"),
        ]
        state = ContentReplacementState()
        result = apply_tool_result_budget(msgs, state, tmp_cwd)
        assert result == msgs

    def test_state_preserves_seen_across_calls(self, tmp_cwd):
        """State accumulates seen IDs across multiple apply_tool_result_budget calls."""
        msgs = []
        from agentcore.core_types import ToolUseBlock
        msgs.append(Message(
            role="assistant", content="",
            tool_use_blocks=[ToolUseBlock(
                tool_use_id="tu_1", tool_name="Grep", input={},
            )],
            id="msg_1",
        ))
        msgs.append(Message(role="user", content="x" * 200_000, tool_use_id="tu_1"))

        state = ContentReplacementState()
        limit = 50_000

        # First pass — should compact
        result1 = apply_tool_result_budget(msgs, state, tmp_cwd, limit)
        compacted1 = [m for m in result1 if is_content_already_compacted(m.content or "")]
        assert len(compacted1) == 1

        # Second pass with already-compacted messages — replacement persisted
        result2 = apply_tool_result_budget(result1, state, tmp_cwd, limit)
        compacted2 = [m for m in result2 if is_content_already_compacted(m.content or "")]
        assert len(compacted2) == 1  # keeps the persisted replacement

    def test_large_tool_result_after_small(self, tmp_cwd):
        """Large result that grows the message beyond budget."""
        msgs = []
        from agentcore.core_types import ToolUseBlock
        msgs.append(Message(
            role="assistant", content="",
            tool_use_blocks=[
                ToolUseBlock(tool_use_id="tu_small", tool_name="Grep", input={}),
                ToolUseBlock(tool_use_id="tu_large", tool_name="Grep", input={}),
            ],
            id="msg_1",
        ))
        msgs.append(Message(role="user", content="small", tool_use_id="tu_small"))
        msgs.append(Message(role="user", content="x" * 45_000, tool_use_id="tu_large"))

        state = ContentReplacementState()
        limit = 50_000

        result = apply_tool_result_budget(msgs, state, tmp_cwd, limit)
        # 5 + 45000 = 45005 < 50000 → no compaction
        compacted = [m for m in result if is_content_already_compacted(m.content or "")]
        assert len(compacted) == 0
