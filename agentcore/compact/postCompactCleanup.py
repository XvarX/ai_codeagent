"""Post-compaction cleanup — mirrors compact/postCompactCleanup.ts.

After compaction, we may want to re-read recently accessed files
and re-inject system context that was lost in the compression.
"""

from pathlib import Path


async def re_read_recent_files(
    tools: dict,  # ToolRegistry or dict of name -> tool
    messages: list,  # list of Message
    max_files: int = 5,
    cwd: str | Path | None = None,
) -> list[str]:
    """Re-read files that were accessed in the preserved (recent) messages.

    Returns a list of file paths that were re-read (for logging).
    """
    from tools.file_read import FileReadTool

    file_tool = None
    if hasattr(tools, 'get'):
        file_tool = tools.get("FileRead")
    elif "FileRead" in tools:
        file_tool = tools["FileRead"]

    if not file_tool or not isinstance(file_tool, FileReadTool):
        return []

    # Find file paths referenced in recent messages
    seen_files: set[str] = set()
    for msg in messages:
        if msg.has_tool_uses:
            for block in msg.tool_use_blocks:
                if block.tool_name == "FileRead" and "file_path" in block.input:
                    seen_files.add(block.input["file_path"])

    re_read: list[str] = []
    from tools.base import ToolContext

    ctx = ToolContext(cwd=Path(cwd) if cwd else Path.cwd())

    for file_path in list(seen_files)[:max_files]:
        try:
            await file_tool.call({"file_path": file_path}, ctx)
            re_read.append(file_path)
        except Exception:
            pass

    return re_read


def add_compact_boundary(
    messages: list,
    pre_tokens: int,
    post_tokens: int,
    trigger: str = "auto",
) -> None:
    """Add a system message marking the compaction boundary.

    This is inserted before the compacted context starts.
    """
    from core_types import Message

    boundary = Message(
        role="user",
        content=(
            f"[Compact boundary: {trigger}]\n"
            f"Context reduced from ~{pre_tokens} to ~{post_tokens} tokens"
        ),
    )
    # Insert at position 0 (before compacted content)
    messages.insert(0, boundary)
