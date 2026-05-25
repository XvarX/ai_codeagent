"""Auto-compact trigger — mirrors compact/autoCompact.ts.

Decides when to trigger compaction based on token estimates
and model context window limits.
"""

from core_types import Message
from compact.grouping import estimate_tokens, group_by_api_round


# Model context window sizes (input tokens)
MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-sonnet-4-6": 200000,
    "claude-sonnet-4-5": 200000,
    "claude-haiku-4-5": 200000,
    "claude-opus-4-7": 200000,
    "claude-opus-4-6": 200000,
    "glm-4.7": 128000,
    "glm-4.5": 128000,
    "glm-4": 128000,
    "gpt-4o": 128000,
    "gpt-4-turbo": 128000,
    "deepseek-chat": 64000,
    "deepseek-v3": 64000,
}

# Reserve space for output and overhead
RESERVED_OUTPUT = 8000
DEFAULT_CONTEXT_WINDOW = 128000


def get_context_window(model: str | None) -> int:
    """Get the effective context window size for a model."""
    if not model:
        return DEFAULT_CONTEXT_WINDOW
    for prefix, size in MODEL_CONTEXT_WINDOWS.items():
        if model.startswith(prefix):
            return size
    return DEFAULT_CONTEXT_WINDOW


def should_auto_compact(
    messages: list[Message],
    model: str | None = None,
    threshold: float = 0.85,
    actual_base: int = 0,
    context_window: int = 0,
    reserved_output: int = 8000,
) -> bool:
    """Check if token count exceeds the auto-compact threshold.

    Uses actual token count from last API response as base,
    plus estimated tokens from messages added since then.

    Triggers when actual + estimated exceeds threshold% of context window.
    """
    if context_window <= 0:
        context_window = get_context_window(model)
    effective = context_window - reserved_output
    max_threshold = int(effective * threshold)

    # Use actual tokens from last API call if available
    if actual_base > 0:
        total = actual_base
    else:
        total = estimate_tokens(messages)

    # Also check that we have enough messages to compact meaningfully
    groups = group_by_api_round(messages)
    if len(groups) < 3:
        return False

    return total > max_threshold
