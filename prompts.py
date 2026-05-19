"""System prompt assembly — mirrors constants/prompts.ts getSystemPrompt().

Two pipes to the LLM:
管道一: System prompt text — tells the model what tools exist and how to use them
管道二: API tools[] schemas — structured definitions enabling actual tool calls
"""

from datetime import datetime


def build_system_prompt(tool_names: list[str], cwd: str) -> str:
    """
    Build the full system prompt string.
    Static section (cacheable) + dynamic section (date, cwd).
    """
    sections = [
        _get_role_section(),
        _get_doing_tasks_section(),
        _get_using_your_tools_section(tool_names),
        _get_tone_section(),
        _get_dynamic_section(cwd),
    ]
    return "\n\n".join(s for s in sections if s)


def _get_role_section() -> str:
    return (
        "You are an interactive coding agent that helps users with "
        "software engineering tasks. You work in the user's terminal, "
        "reading and editing files in their project directory."
    )


def _get_doing_tasks_section() -> str:
    return (
        "# Doing tasks\n\n"
        "The user will ask you to perform software engineering tasks. "
        "These may include fixing bugs, adding new functionality, "
        "refactoring code, explaining code, and more.\n\n"
        "- Prefer editing existing files to creating new ones.\n"
        "- Be careful not to introduce security vulnerabilities.\n"
        "- Don't add features, refactor, or introduce abstractions "
        "beyond what the task requires.\n"
        "- Default to writing no comments."
    )


def _get_using_your_tools_section(tool_names: list[str]) -> str:
    """Generate tool usage guidance (mirrors getUsingYourToolsSection in prompts.ts)."""
    lines = [
        "# Using your tools",
        "",
        "You have access to a set of tools for file operations and system commands.",
        "Prefer dedicated tools over Bash when available:",
        "",
    ]

    tool_guidance = {
        "FileRead": "To read files use FileRead instead of cat, head, or tail",
        "FileEdit": "To edit files use FileEdit instead of sed or awk",
        "FileWrite": "To create files use FileWrite instead of cat with heredoc or echo redirection",
        "Glob": "To search for files by pattern use Glob instead of find or ls",
        "Grep": "To search file contents use Grep instead of grep or rg",
        "Bash": (
            "Reserve Bash exclusively for system commands and terminal operations "
            "that require shell execution. If there is a relevant dedicated tool, "
            "default to using it and only fall back to Bash when absolutely necessary."
        ),
    }

    for name in tool_names:
        if name in tool_guidance:
            lines.append(f"- {tool_guidance[name]}")

    lines.extend([
        "",
        "You can call multiple tools in a single response. When there are no "
        "dependencies between them, make all independent tool calls in parallel. "
        "If some tool calls depend on previous calls, run them sequentially instead.",
    ])

    return "\n".join(lines)


def _get_tone_section() -> str:
    return (
        "# Tone and style\n\n"
        "Keep responses short and direct. "
        "Default to writing no comments in code. "
        "Only explain when the WHY is non-obvious."
    )


def _get_dynamic_section(cwd: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        "# Environment\n\n"
        f"Current date: {now}\n"
        f"Working directory: {cwd}\n"
    )
