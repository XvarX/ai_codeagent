"""Micro-compaction — lightweight context reduction without API call.

Mirrors compact/microCompact.ts. Replaces old tool result content with
placeholder text to reduce token usage without invalidating prompt cache.
"""

from core_types import Message
from compact.grouping import group_by_api_round

# Tools whose results are safe to trim (non-critical for context)
COMPACTABLE_TOOLS = {"Bash", "FileRead", "Grep", "Glob", "FileEdit", "FileWrite"}

# Keep tool results in the most recent N API rounds verbatim
KEEP_RECENT_ROUNDS = 2


def micro_compact(messages: list[Message]) -> list[Message]:
    """Replace old tool results with placeholder text.

    Groups messages by API round, keeps tool results in the most
    recent 2 rounds verbatim, replaces older ones with placeholder.
    """
    groups = group_by_api_round(messages)
    if len(groups) <= KEEP_RECENT_ROUNDS:
        return messages

    # Find the cutoff index — start of the keep-recent region
    recent_start = 0
    for g in groups[-KEEP_RECENT_ROUNDS:]:
        recent_start += len(g)
    cutoff_idx = len(messages) - recent_start

    compacted = 0
    for i in range(cutoff_idx):
        msg = messages[i]
        if msg.is_tool_result and msg.role == "user":
            tool_name = _find_tool_name(messages, i)
            if tool_name in COMPACTABLE_TOOLS and msg.content:
                msg.content = (
                    f"[Old tool result ({tool_name}) — content cleared by micro-compaction]"
                )
                compacted += 1

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
