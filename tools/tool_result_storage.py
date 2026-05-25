"""Tool result persistence — mirrors toolResultStorage.ts.

Two-layer mechanism:
  1. processToolResultBlock — per-tool persistence when result exceeds max_result_chars
  2. applyToolResultBudget — per-message aggregate budget enforcement before next LLM call
"""

import json
import os
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field

from core_types import Message


# --- Constants ---
DEFAULT_MAX_RESULT_CHARS = 50_000
MAX_TOOL_RESULTS_PER_MESSAGE_CHARS = 200_000
PREVIEW_SIZE_CHARS = 500
TOOL_RESULTS_DIR = ".myagent/tool_results"


def _get_tool_results_dir(cwd: Path) -> Path:
    d = cwd / TOOL_RESULTS_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


# --- Persistence ---
def persist_tool_result(content: str, tool_use_id: str, cwd: Path) -> str:
    """Write tool result to disk, return replacement text."""
    results_dir = _get_tool_results_dir(cwd)
    filename = f"{tool_use_id}.json"
    filepath = results_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({"content": content}, f, ensure_ascii=False)

    preview = content[:PREVIEW_SIZE_CHARS].replace("\n", " ")
    return (
        f"<persisted-output>\n"
        f"Preview: {preview}{'...' if len(content) > PREVIEW_SIZE_CHARS else ''}\n"
        f"[{len(content)} chars saved to {TOOL_RESULTS_DIR}/{filename}]\n"
        f"</persisted-output>"
    )


def is_content_already_compacted(content: str) -> bool:
    """True if content was already replaced by persist-to-file."""
    return content.startswith("<persisted-output>")


# --- Layer 1: Per-tool persistence ---
def process_tool_result_block(
    result_text: str,
    tool_name: str,
    tool_use_id: str,
    max_result_chars: int | None,
    cwd: Path,
) -> str:
    """If result exceeds tool's limit, persist to disk and return replacement text.

    FileRead tools (max_result_chars=None) are never persisted.
    """
    if max_result_chars is None:
        return result_text  # FileRead: never persist

    threshold = min(max_result_chars, DEFAULT_MAX_RESULT_CHARS)

    if len(result_text) <= threshold:
        return result_text

    return persist_tool_result(result_text, tool_use_id, cwd)


# --- State tracking for Layer 2 ---
@dataclass
class ContentReplacementState:
    """Tracks tool result replacement decisions across turns."""
    seen_ids: set[str] = field(default_factory=set)
    replacements: dict[str, str] = field(default_factory=dict)


# --- Layer 2: Per-message budget ---
@dataclass
class ToolResultCandidate:
    tool_use_id: str
    content: str
    size: int


def _collect_candidates_by_message(
    messages: list[Message],
    state: ContentReplacementState,
) -> list[list[ToolResultCandidate]]:
    """Group fresh tool_results by their containing user message."""
    groups: list[list[ToolResultCandidate]] = []
    current: list[ToolResultCandidate] = []
    last_asst_id: str | None = None

    for msg in messages:
        if msg.role == "assistant" and msg.has_tool_uses:
            msg_id = getattr(msg, "id", None) or str(id(msg))
            if msg_id != last_asst_id:
                if current:
                    groups.append(current)
                    current = []
                last_asst_id = msg_id
        elif msg.role == "user" and msg.tool_use_id:
            if is_content_already_compacted(msg.content or ""):
                state.seen_ids.add(msg.tool_use_id)
                continue
            if msg.tool_use_id not in state.seen_ids:
                current.append(ToolResultCandidate(
                    tool_use_id=msg.tool_use_id,
                    content=msg.content or "",
                    size=len(msg.content or ""),
                ))

    if current:
        groups.append(current)
    return groups


def _select_fresh_to_replace(
    fresh: list[ToolResultCandidate],
    frozen_size: int,
    limit: int,
) -> list[ToolResultCandidate]:
    """Pick the largest results to replace until total is under budget."""
    sorted_candidates = sorted(fresh, key=lambda c: c.size, reverse=True)
    selected: list[ToolResultCandidate] = []
    remaining = frozen_size + sum(c.size for c in fresh)

    for c in sorted_candidates:
        if remaining <= limit:
            break
        selected.append(c)
        remaining -= c.size

    return selected


def apply_tool_result_budget(
    messages: list[Message],
    state: ContentReplacementState,
    cwd: Path,
    limit: int = MAX_TOOL_RESULTS_PER_MESSAGE_CHARS,
) -> list[Message]:
    """Enforce per-message budget on tool result aggregate size.

    For each user message with fresh tool_results exceeding the limit,
    persist the largest ones and replace with previews.
    """
    if state is None:
        return messages

    groups = _collect_candidates_by_message(messages, state)
    replacement_map: dict[str, str] = {}

    for candidates in groups:
        # Separate: must reapply, frozen, fresh
        to_reapply: dict[str, str] = {}
        frozen_size = 0
        fresh: list[ToolResultCandidate] = []

        for c in candidates:
            repl = state.replacements.get(c.tool_use_id)
            if repl is not None:
                to_reapply[c.tool_use_id] = repl
            elif c.tool_use_id in state.seen_ids:
                frozen_size += c.size
            else:
                fresh.append(c)

        # Reapply cached replacements
        replacement_map.update(to_reapply)

        if not fresh:
            continue

        fresh_size = sum(c.size for c in fresh)
        if frozen_size + fresh_size <= limit:
            # Under budget — mark as seen, keep all
            for c in fresh:
                state.seen_ids.add(c.tool_use_id)
            continue

        # Over budget — pick largest to replace
        selected = _select_fresh_to_replace(fresh, frozen_size, limit)
        selected_ids = {c.tool_use_id for c in selected}

        for c in fresh:
            if c.tool_use_id not in selected_ids:
                state.seen_ids.add(c.tool_use_id)

        for c in selected:
            replacement = persist_tool_result(c.content, c.tool_use_id, cwd)
            state.seen_ids.add(c.tool_use_id)
            state.replacements[c.tool_use_id] = replacement
            replacement_map[c.tool_use_id] = replacement

    if not replacement_map:
        return messages

    # Apply replacements to messages
    result = []
    for msg in messages:
        if msg.role == "user" and msg.tool_use_id and msg.tool_use_id in replacement_map:
            new_msg = Message(
                role="user",
                content=replacement_map[msg.tool_use_id],
                tool_use_id=msg.tool_use_id,
            )
            result.append(new_msg)
        else:
            result.append(msg)
    return result
