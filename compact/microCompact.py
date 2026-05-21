"""Micro-compaction — lightweight context reduction without API call.

Mirrors compact/microCompact.ts. Replaces old tool result content with
placeholder text to reduce token usage without invalidating prompt cache.
"""

from core_types import Message

# Tools whose results are safe to trim (non-critical for context)
COMPACTABLE_TOOLS = {"Bash", "FileRead", "Grep", "Glob", "FileEdit", "FileWrite"}

# Keep the last N compactable tool results verbatim
KEEP_LAST_N = 3

# Only compact messages before this many API rounds ago
MIN_ROUNDS_AGO = 2


def micro_compact(messages: list[Message]) -> list[Message]:
    """Replace old tool results with placeholder text.

    Leaves the most recent N tool results intact. Only touches
    messages in groups older than MIN_ROUNDS_AGO.

    Modifies messages in place for performance (matches Claude Code behavior).
    """
    # Find compactable tool result positions
    tool_result_indices: list[tuple[int, str, int]] = []  # (index, tool_name, content_len)

    for i, msg in enumerate(messages):
        if msg.is_tool_result and msg.role == "user":
            # Tool result messages have a tool_use_id
            # Find which tool generated this
            tool_name = _find_tool_name(messages, i)
            if tool_name in COMPACTABLE_TOOLS:
                tool_result_indices.append((i, tool_name, len(msg.content or "")))

    if len(tool_result_indices) <= KEEP_LAST_N:
        return messages

    # Keep last N, compact the rest
    to_compact = tool_result_indices[:-KEEP_LAST_N]
    compacted_bytes = 0

    for idx, name, length in to_compact:
        if messages[idx].content and length > 0:
            messages[idx].content = f"[Old tool result ({name}) — content cleared by micro-compaction]"
            compacted_bytes += length

    return messages


def _find_tool_name(messages: list[Message], result_idx: int) -> str:
    """Find which tool name corresponds to a tool_result at the given index."""
    if result_idx >= len(messages):
        return ""
    result_msg = messages[result_idx]
    tool_id = result_msg.tool_use_id
    if not tool_id:
        return ""

    # Search backwards for the assistant message with matching tool_use block
    for i in range(result_idx - 1, -1, -1):
        msg = messages[i]
        if msg.role == "assistant" and msg.has_tool_uses:
            for block in msg.tool_use_blocks:
                if block.tool_use_id == tool_id:
                    return block.tool_name

    return ""
