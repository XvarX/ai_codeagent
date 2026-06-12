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
        _get_chatroom_section(),
        _get_private_message_section(),
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


def _get_chatroom_section() -> str:
    return (
        "# 聊天室 (Chat Rooms)\n\n"
        "你所在的聊天室信息会在每次对话轮次中注入。消息格式：\n\n"
        "```\n"
        "[Room: 聊天室名称 | From: 发送者 | To: 接收者]\n"
        "消息正文\n"
        "```\n\n"
        "回复规则：\n"
        "- To 指明消息目标。需要回复的情况：To 明确指向你、面向全体、"
        "通过内容上下文判断是在跟你对话、或内容有明显错误需要纠正\n"
        "- 不是对你的、不是对全体的、且内容没有错误时，不需要回复\n"
        "- 需要回复时必须用 BroadcastRoom 工具回复（直接在对话中回复用户看不到），to 参数指定回复对象\n"
        "- 达成共识后停止广播，不要无意义来回广播\n"
    )


def _get_private_message_section() -> str:
    return (
        "# 私聊 (Private Messages)\n\n"
        "其他 Agent 可能通过 SendMessage 向你发送私聊。私聊消息格式：\n\n"
        "```\n"
        "[Message from 发送者 (id:ID)]\n"
        "消息正文\n"
        "```\n\n"
        "回复规则：\n"
        "- 如需回复，只能用 SendMessage 私聊回复，不能使用 BroadcastRoom\n"
        "- 内容不涉及你、无需回复时可以不回应\n"
    )


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
