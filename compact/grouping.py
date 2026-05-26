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


def _normalize_usage(usage: dict) -> dict:
    """Normalize usage to OpenAI format {prompt_tokens, completion_tokens, total_tokens}."""
    if not usage:
        return {}
    if "prompt_tokens" not in usage and "input_tokens" in usage:
        input_total = (
            (usage.get("input_tokens") or 0)
            + (usage.get("cache_creation_input_tokens") or 0)
            + (usage.get("cache_read_input_tokens") or 0)
        )
        output = usage.get("output_tokens") or 0
        return {
            "prompt_tokens": input_total,
            "completion_tokens": output,
            "total_tokens": input_total + output,
        }
    if "total_tokens" not in usage:
        usage["total_tokens"] = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
    return usage


def estimate_tokens(messages: list[Message]) -> int:
    """Rough token count for a list of messages (chars / 2.5 for mixed)."""
    return estimate_tokens_with_usage(messages)


def estimate_tokens_with_usage(messages: list[Message]) -> int:
    """Token count using API usage as baseline for accuracy.

    Walks messages backwards, finds the last assistant message with
    actual API usage data. Uses that as the baseline and adds rough
    estimation for subsequent messages after it.
    """
    # Walk backwards to find last assistant with usage
    baseline = 0
    subsequent = []
    found_usage = False

    for msg in reversed(messages):
        if not found_usage and msg.role == "assistant" and msg.usage:
            norm = _normalize_usage(msg.usage)
            baseline = norm.get("total_tokens", 0)
            found_usage = True
        elif found_usage:
            subsequent.append(msg)

    if not found_usage:
        # No usage data — fallback to pure rough estimation
        total = 0
        for msg in messages:
            total += len(msg.content or "")
            for block in msg.tool_use_blocks:
                total += len(str(block.input))
        return int(total / 4 * 4 / 3)

    # Rough estimation for messages after the baselined assistant
    extra = 0
    for msg in subsequent:
        extra += len(msg.content or "")
        for block in msg.tool_use_blocks:
            extra += len(str(block.input))

    return baseline + int(extra / 2.5)
