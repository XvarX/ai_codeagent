"""Micro-compaction — lightweight context reduction without API call.

Matches Claude Code's timeBasedMC: triggers when (1) compactable tool results > 5
AND (2) gap since last assistant message > 60 min (server cache expired).

Keeps the last 5 compactable results, clears older ones with placeholder.
"""

from time import time
from core_types import Message

COMPACTABLE_TOOLS = {"Bash", "FileRead", "Grep", "Glob", "FileEdit", "FileWrite"}
KEEP_RECENT = 5
GAP_THRESHOLD_MINUTES = 60


def micro_compact(messages: list[Message]) -> list[Message]:
    """Clear old tool results if trigger conditions are met.

    1. > KEEP_RECENT compactable tool results
    2. Last assistant message > GAP_THRESHOLD_MINUTES ago
    """
    # Condition 1: enough compactable results?
    tool_results: list[tuple[int, str, str]] = []
    for i, msg in enumerate(messages):
        if msg.is_tool_result and msg.role == "user":
            name = _find_tool_name(messages, i)
            if name in COMPACTABLE_TOOLS:
                tool_results.append((i, name, msg.tool_use_id or ""))

    if len(tool_results) <= KEEP_RECENT:
        return messages

    # Condition 2: time gap since last assistant?
    last_asst = _find_last_assistant(messages)
    if last_asst is not None:
        gap_minutes = (time() - last_asst.timestamp) / 60
        if gap_minutes < GAP_THRESHOLD_MINUTES:
            return messages  # cache still warm, don't compact

    # Both conditions met — clear old results
    keep_ids = {tid for _, _, tid in tool_results[-KEEP_RECENT:]}
    for idx, name, tid in tool_results[:-KEEP_RECENT]:
        if tid not in keep_ids and messages[idx].content:
            messages[idx].content = (
                f"[Old tool result ({name}) — content cleared]"
            )

    return messages


def _find_last_assistant(messages: list[Message]) -> Message | None:
    """Find the most recent assistant message."""
    for msg in reversed(messages):
        if msg.role == "assistant":
            return msg
    return None


def _find_tool_name(messages: list[Message], result_idx: int) -> str:
    """Find which tool name corresponds to a tool_result at the given index."""
    if result_idx >= len(messages):
        return ""
    result_msg = messages[result_idx]
    tool_id = result_msg.tool_use_id
    if not tool_id:
        return ""

    for i in range(result_idx - 1, -1, -1):
        msg = messages[i]
        if msg.role == "assistant" and msg.has_tool_uses:
            for block in msg.tool_use_blocks:
                if block.tool_use_id == tool_id:
                    return block.tool_name

    return ""
