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
    Skills are injected as a user-role system reminder each turn.
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
        "Do NOT use Bash to run commands when a relevant dedicated tool is provided. "
        "Using dedicated tools allows the user to better understand and review your work. "
        "This is CRITICAL to assisting the user:",
        "",
    ]

    tool_names_set = set(tool_names)

    if "FileRead" in tool_names_set:
        lines.append("- To read files use FileRead instead of cat, head, tail, or sed")
    if "FileEdit" in tool_names_set:
        lines.append("- To edit files use FileEdit instead of sed or awk")
    if "FileWrite" in tool_names_set:
        lines.append("- To create files use FileWrite instead of cat with heredoc or echo redirection")
    if "Glob" in tool_names_set:
        lines.append("- To search for files by name use Glob instead of find or ls")
    if "Grep" in tool_names_set:
        lines.append("- To search file contents use Grep instead of grep or rg")
    if "Bash" in tool_names_set:
        lines.append(
            "- Reserve using Bash exclusively for system commands and terminal operations "
            "that require shell execution. If you are unsure and there is a relevant "
            "dedicated tool, default to using the dedicated tool and only fallback on "
            "Bash if it is absolutely necessary."
        )

    lines.append("")
    lines.append(
        "You can call multiple tools in a single response. If you intend to call "
        "multiple tools and there are no dependencies between them, make all "
        "independent tool calls in parallel. Maximize use of parallel tool calls "
        "where possible to increase efficiency."
    )

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
