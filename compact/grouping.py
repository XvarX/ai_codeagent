"""Message grouping by API round — mirrors compact/grouping.ts.

Each new assistant Message starts a new group. Groups are the atomic unit
for truncation and partial compaction.
"""

from core_types import Message


def group_by_api_round(messages: list[Message]) -> list[list[Message]]:
    """Split messages into API-round groups.

    A new group starts at each assistant message (not tool_result).
    This ensures tool_use/tool_result pairs stay with their assistant response.
    """
    groups: list[list[Message]] = []
    current: list[Message] = []

    for msg in messages:
        if msg.role == "assistant" and current:
            groups.append(current)
            current = [msg]
        else:
            current.append(msg)

    if current:
        groups.append(current)

    return groups


def estimate_tokens(messages: list[Message]) -> int:
    """Rough token count for a list of messages (chars / 2.5 for mixed)."""
    total = 0
    for msg in messages:
        total += len(msg.content or "")
        for block in msg.tool_use_blocks:
            total += len(str(block.input))
    return int(total / 2.5)
