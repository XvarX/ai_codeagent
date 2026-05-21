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
    log_path: str | None = None,
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

    # 5. Re-read recently accessed files (mirrors createPostCompactFileAttachments)
    # old_messages has the compacted section; recent_messages is the preserved tail
    file_messages = await _re_read_recent_files(
        old_messages, preserved=recent_messages, max_files=3
    )

    # 6. Build post-compact message list
    boundary = Message(
        role="user",
        content=(
            "[Context compressed — earlier conversation summarized below]\n\n"
            f"{summary_text}\n\n"
            "[End of compressed context]"
        ),
    )

    summary_messages = [boundary] + file_messages
    post_tokens = estimate_tokens(summary_messages + recent_messages)

    # Log compact request/response if log_path provided
    if log_path:
        import json
        with open(log_path, "a", encoding="utf-8") as lf:
            lf.write("\n" + "=" * 40 + " COMPACT " + "=" * 40 + "\n")
            lf.write("── Compact API Request ──\n")
            req_info = {
                "model": getattr(provider, "model", "?"),
                "messages_count": len(compact_messages),
                "tools": [],
                "system": COMPACT_SYSTEM_PROMPT[:200] + "...",
            }
            lf.write(json.dumps(req_info, ensure_ascii=False, indent=2) + "\n\n")
            lf.write(f"── Compact Result ──\n")
            lf.write(f"Pre-tokens: ~{pre_tokens}\n")
            lf.write(f"Post-tokens: ~{post_tokens}\n")
            lf.write(f"Files restored: {len(file_messages)}\n")
            lf.write(f"Summary:\n{summary_text[:1000]}\n")
            lf.write("─" * 90 + "\n")

    return CompactionResult(
        summary_messages=summary_messages,
        messages_to_keep=recent_messages,
        pre_tokens=pre_tokens,
        post_tokens=post_tokens,
    )


async def _re_read_recent_files(
    compacted: list[Message],
    preserved: list[Message],
    max_files: int = 3,
) -> list[Message]:
    """Re-read recently accessed files after compaction.

    Collects FileRead paths from the compacted messages, excludes files
    already referenced in preserved messages (no duplicates), re-reads the
    most recent 3 files. Mirrors createPostCompactFileAttachments.
    """
    # Paths already visible in preserved messages — don't re-inject
    preserved_paths: set[str] = set()
    for msg in preserved:
        if msg.has_tool_uses:
            for block in msg.tool_use_blocks:
                if block.tool_name == "FileRead" and "file_path" in block.input:
                    preserved_paths.add(block.input["file_path"])

    # Paths from the compacted section, in order, no duplicates
    compacted_paths: list[str] = []
    for msg in compacted:
        if msg.has_tool_uses:
            for block in msg.tool_use_blocks:
                if block.tool_name == "FileRead" and "file_path" in block.input:
                    path = block.input["file_path"]
                    if path not in compacted_paths:
                        compacted_paths.append(path)

    # Filter: skip plan/CLAUDE files and already-in-preserved files
    candidates = [
        p for p in compacted_paths
        if p not in preserved_paths
        and not p.endswith((".yaml", ".yml", ".md"))
    ]
    if not candidates:
        return []

    # Take most recent N, re-read
    result_messages: list[Message] = []
    for path in candidates[-max_files:]:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            if len(content) > 2000:
                content = content[:2000] + "\n... [truncated]"
            result_messages.append(Message(
                role="user",
                content=(
                    f"[Post-compact file restore: {path}]\n"
                    f"{content}\n"
                    f"[/file: {path}]"
                ),
            ))
        except Exception:
            pass

    return result_messages


def _fallback_summary(messages: list[Message], reason: str = "LLM call failed") -> str:
    """Fallback when LLM summarization fails — just list user messages."""
    user_msgs = [m for m in messages if m.role == "user" and not m.is_tool_result]
    lines = [f"## Conversation Summary ({reason})\n"]
    for m in user_msgs:
        preview = (m.content or "")[:200].replace("\n", " ")
        lines.append(f"- {preview}")
    return "\n".join(lines)
