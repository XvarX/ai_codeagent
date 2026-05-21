"""Core compaction engine — mirrors compact/compact.ts compactConversation().

Sends old conversation to LLM for summarization, replaces old messages
with a structured summary + compact boundary marker.
"""

from core_types import Message, ToolUseBlock
from compact.grouping import group_by_api_round, estimate_tokens
from compact.prompt import (
    COMPACT_SYSTEM_PROMPT,
    build_compact_user_message,
    format_summary,
)


class CompactionResult:
    """Result of a compaction operation."""

    def __init__(
        self,
        summary_messages: list[Message],
        messages_to_keep: list[Message],
        pre_tokens: int,
        post_tokens: int,
    ):
        self.summary_messages = summary_messages  # boundary marker + summary
        self.messages_to_keep = messages_to_keep  # recent messages kept verbatim
        self.pre_tokens = pre_tokens
        self.post_tokens = post_tokens


# Max output tokens for the compaction LLM call
COMPACT_MAX_OUTPUT_TOKENS = 4000
COMPACT_MODEL = None  # None = use same model as main conversation


async def compact_conversation(
    provider,
    messages: list[Message],
    tools_schema: list[dict],
    keep_recent_rounds: int = 2,
) -> CompactionResult:
    """Summarize old messages via LLM, keep recent rounds verbatim.

    Returns a CompactionResult with:
    - boundary marker + summary text (new messages to prepend)
    - recent messages kept verbatim
    - token counts before/after
    """
    # 1. Group messages by API round
    groups = group_by_api_round(messages)
    if len(groups) <= keep_recent_rounds + 1:
        # Not enough to compact
        return CompactionResult([], messages, estimate_tokens(messages), estimate_tokens(messages))

    # 2. Split into old (to summarize) and recent (to keep)
    old_groups = groups[:-keep_recent_rounds]
    recent_groups = groups[-keep_recent_rounds:]
    old_messages = [m for g in old_groups for m in g]
    recent_messages = [m for g in recent_groups for m in g]
    pre_tokens = estimate_tokens(messages)

    # 3. Build compaction request messages
    compact_messages = list(old_messages)  # copy for API
    compact_messages.append(Message(
        role="user",
        content=build_compact_user_message(),
    ))

    # 4. Call LLM for summary (with tools disabled to force text-only)
    import asyncio
    try:
        assistant_msg, tool_blocks, raw = await asyncio.wait_for(
            provider.call(
                messages=compact_messages,
                tools=[],
                system=COMPACT_SYSTEM_PROMPT,
            ),
            timeout=120,  # 2 minutes max for compaction
        )
        summary_text = assistant_msg.content or ""
        summary_text = format_summary(summary_text)
    except asyncio.TimeoutError:
        summary_text = _fallback_summary(old_messages, "compaction timed out")
    except Exception:
        summary_text = _fallback_summary(old_messages)

    # 5. Build post-compact message list
    boundary = Message(
        role="user",
        content=(
            "[Context compressed — earlier conversation summarized below]\n\n"
            f"{summary_text}\n\n"
            "[End of compressed context]"
        ),
    )

    summary_messages = [boundary]
    post_tokens = estimate_tokens(summary_messages + recent_messages)

    return CompactionResult(
        summary_messages=summary_messages,
        messages_to_keep=recent_messages,
        pre_tokens=pre_tokens,
        post_tokens=post_tokens,
    )


def _fallback_summary(messages: list[Message], reason: str = "LLM call failed") -> str:
    """Fallback when LLM summarization fails — just list user messages."""
    user_msgs = [m for m in messages if m.role == "user" and not m.is_tool_result]
    lines = [f"## Conversation Summary ({reason})\n"]
    for m in user_msgs:
        preview = (m.content or "")[:200].replace("\n", " ")
        lines.append(f"- {preview}")
    return "\n".join(lines)
