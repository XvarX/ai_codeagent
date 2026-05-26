"""Message grouping by API round — mirrors compact/grouping.ts.

Two grouping modes:
- by_api_round: splits at each assistant message (per-LLM-call)
- by_user_round: splits at each user message (per-send, excludes tool_results)
"""

from core_types import Message


def group_by_api_round(messages: list[Message]) -> list[list[Message]]:
    """Split messages into API-round groups.

    A new group starts at:
    - each new assistant message with a different message.id
    - each new user message (not tool_result)

    This ensures tool_use/tool_result pairs stay with their assistant response
    and user turns are independently grouped.
    """
    groups: list[list[Message]] = []
    current: list[Message] = []
    last_asst_id: str | None = None

    for msg in messages:
        if msg.role == "assistant" and msg.id and msg.id != last_asst_id and current:
            groups.append(current)
            current = [msg]
        elif msg.role == "user" and not msg.is_tool_result and current:
            groups.append(current)
            current = [msg]
        else:
            current.append(msg)
        if msg.role == "assistant" and msg.id:
            last_asst_id = msg.id

    if current:
        groups.append(current)

    return groups


def group_by_user_round(messages: list[Message]) -> list[list[Message]]:
    """Split messages by user conversation round.

    A new group starts at each user message (not a tool_result).
    One user send + all subsequent LLM responses/tool calls = one round.
    Used for micro-compaction keep-recent logic.
    """
    groups: list[list[Message]] = []
    current: list[Message] = []

    for msg in messages:
        if msg.role == "user" and not msg.is_tool_result and current:
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
