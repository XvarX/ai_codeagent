"""Micro-compaction — lightweight context reduction without API call.

Matches Claude Code's timeBasedMC: keeps the last N compactable tool
results verbatim, clears older ones with placeholder text.
"""

from core_types import Message

# Tools whose results are safe to trim (non-critical for context)
COMPACTABLE_TOOLS = {"Bash", "FileRead", "Grep", "Glob", "FileEdit", "FileWrite"}

# Keep the most recent N compactable tool results (matches Claude Code default)
KEEP_RECENT = 5


def micro_compact(messages: list[Message]) -> list[Message]:
    """Clear old tool result content, keeping the most recent KEEP_RECENT.

    Collects all compactable tool results by their tool_use_id,
    keeps the last KEEP_RECENT, replaces older content with placeholder.
    """
    # Collect all compactable tool results: (index, tool_name, tool_use_id)
    tool_results: list[tuple[int, str, str]] = []
    for i, msg in enumerate(messages):
        if msg.is_tool_result and msg.role == "user":
            name = _find_tool_name(messages, i)
            if name in COMPACTABLE_TOOLS:
                tool_results.append((i, name, msg.tool_use_id or ""))

    if len(tool_results) <= KEEP_RECENT:
        return messages

    # Keep last N, compact the rest
    keep_ids = {tid for _, _, tid in tool_results[-KEEP_RECENT:]}

    for idx, name, tid in tool_results[:-KEEP_RECENT]:
        if tid not in keep_ids and messages[idx].content:
            messages[idx].content = (
                f"[Old tool result ({name}) — content cleared]"
            )

    return messages


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
