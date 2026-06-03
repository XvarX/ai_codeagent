"""Compaction prompt templates — mirrors compact/prompt.ts."""

COMPACT_SYSTEM_PROMPT = """You are compressing a conversation history for an AI coding agent.
Your job is to create a concise but complete summary of the conversation so far.

## Instructions

1. First, in an <analysis> block, think through what's important and what can be omitted.
2. Then, in a <summary> block, write the structured summary.

## What to Include in the Summary

- **Primary Requests**: All user messages and their explicit requests
- **Key Technical Concepts**: Technologies, frameworks, APIs discussed
- **Files and Code**: Files read, edited, or created, with key code changes
- **Errors and Fixes**: Bugs encountered and how they were resolved
- **Problem Solving**: Design decisions, architectural choices
- **Pending Tasks**: What still needs to be done
- **Current Work**: What was being worked on most recently

## What to Omit

- Redundant tool calls with unchanged results
- Verbose file contents that were just read and not modified
- Repetitive error messages
- Empty or trivial tool results

## Output Format

<analysis>
[Your thinking — this will be stripped]
</analysis>

<summary>
[The structured summary — this is preserved]
</summary>

Keep the summary concise but comprehensive. The summary will become the only context the model has about the earlier conversation."""


def build_compact_user_message() -> str:
    """The user message sent along with the conversation to be compressed."""
    return (
        "Compress the conversation above into the <summary> format described. "
        "Be thorough — include all user requests, key decisions, file changes, "
        "errors, and pending tasks."
    )


def strip_analysis_block(text: str) -> str:
    """Remove the <analysis> block from the LLM's response."""
    import re
    return re.sub(r"<analysis>.*?</analysis>", "", text, flags=re.DOTALL).strip()


def format_summary(text: str) -> str:
    """Clean up and format the summary text for injection into conversation."""
    text = strip_analysis_block(text)
    # Replace <summary> tags with section headers
    text = text.replace("<summary>", "").replace("</summary>", "")
    return text.strip()
