"""Message grouping by API round — mirrors compact/grouping.ts.

Two grouping modes:
- by_api_round: splits at each assistant message (per-LLM-call)
- by_user_round: splits at each user message (per-send, excludes tool_results)
"""

from agentcore.core_types import Message


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


def compute_group_idx(
    messages: list[Message],
    existing_entries: list[dict],
    group_key: str | None,
) -> int | None:
    """Compute persistent group G-number for a debug entry.

    Uses a two-level gi->gid mapping so that entries surviving compact/snip
    keep their original G-number while new groups get incremented IDs.
    """
    if not group_key:
        return None

    groups = group_by_api_round(messages)

    # Build ID -> gi lookups from current messages
    asst_id_to_gi: dict[str, int] = {}
    tool_id_to_gi: dict[str, int] = {}
    user_msg_groups: list[int] = []
    for gi, g in enumerate(groups):
        for m in g:
            if m.role == "assistant" and m.id:
                asst_id_to_gi[m.id] = gi
            elif m.role == "user" and m.tool_use_id:
                tool_id_to_gi[m.tool_use_id] = gi
            elif m.role == "user" and not m.is_tool_result and not m.tool_use_id:
                content = m.content or ""
                if not content.startswith("[Context compressed"):
                    user_msg_groups.append(gi)

    # Rebuild persistent gi->gid map from surviving existing entries
    persistent: dict[int, int] = {}
    for entry in existing_entries:
        gid = entry.get("group_idx")
        if gid is None or gid < 0 or entry.get("opacity", 1.0) < 1.0:
            continue
        key = entry.get("group_key") or ""
        gi = None
        if key.startswith("asst:"):
            gi = asst_id_to_gi.get(key[5:])
        elif key.startswith("tool:"):
            gi = tool_id_to_gi.get(key[5:])
        if gi is not None:
            persistent[gi] = gid

    max_persistent = max(
        (e.get("group_idx", -1) for e in existing_entries
         if e.get("group_idx") is not None and e.get("group_idx", -1) >= 0
         and e.get("opacity", 1.0) >= 1.0),
        default=-1)
    next_gid = max_persistent + 1

    # Count already-assigned entries to skip
    user_idx = sum(1 for e in existing_entries
                   if e.get("group_key") == "user"
                   and e.get("group_idx") is not None
                   and e.get("opacity", 1.0) >= 1.0)

    # Compute gi for this entry
    gi = None
    if group_key == "user":
        if user_idx < len(user_msg_groups):
            gi = user_msg_groups[user_idx]
        else:
            gi = len(groups)
    elif group_key.startswith("asst:"):
        gi = asst_id_to_gi.get(group_key[5:])
    elif group_key.startswith("tool:"):
        gi = tool_id_to_gi.get(group_key[5:])
        if gi is None:
            for _gi, g in enumerate(groups):
                for m in g:
                    for b in (getattr(m, "tool_use_blocks", None) or []):
                        if b.tool_use_id == group_key[5:]:
                            gi = _gi
                            break

    if gi is None:
        return None

    gid = persistent.get(gi, next_gid)
    return gid


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
