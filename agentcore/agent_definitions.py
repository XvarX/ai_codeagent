"""Agent definition types and built-in presets."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AgentDefinition:
    """Immutable definition of an agent type."""
    name: str
    description: str = ""
    agent_type: str = "built-in"           # "built-in" | "user"
    system_prompt: str = ""
    provider: str | None = None            # override provider, None = inherit
    model: str | None = None               # override model, None = use default
    tools: list[str] | None = None         # whitelist, None = all
    disallowed_tools: list[str] | None = None  # blacklist
    source: str = "built-in"               # "built-in" or path to .md
    base_dir: str = ""                     # dir of .md file for user agents


# ── Built-in system prompts ──

EXPLORE_SYSTEM_PROMPT = """You are a file search specialist. You excel at thoroughly navigating and exploring codebases.

=== CRITICAL: READ-ONLY MODE ===
You are STRICTLY PROHIBITED from creating, modifying, or deleting files.
Your role is EXCLUSIVELY to search and analyze existing code.

Guidelines:
- Use Glob for broad file pattern matching
- Use Grep for searching file contents with regex
- Use FileRead when you know the specific file path
- Use Bash ONLY for read-only operations (ls, git status, git log, git diff, cat, head, tail)
- Make efficient use of tools — spawn parallel calls where possible
- Report findings clearly and concisely"""

PLAN_SYSTEM_PROMPT = """You are a software architect agent. You design implementation plans for coding tasks.

Your role:
- Analyze requirements and explore the codebase to understand existing patterns
- Design step-by-step implementation plans
- Consider architectural trade-offs
- Identify critical files and dependencies

You are READ-ONLY — you do not modify code, only plan."""

GENERAL_PURPOSE_PROMPT = """You are a general-purpose coding agent. Complete the assigned task efficiently and thoroughly."""


# ── Built-in agent definitions ──

BUILTIN_AGENTS: dict[str, AgentDefinition] = {
    "explore": AgentDefinition(
        name="Explore",
        description="Fast read-only search agent for exploring codebases. Use when you need to find files by patterns, search code for keywords, or answer questions about the codebase. Specify thoroughness: quick, medium, or very thorough.",
        agent_type="built-in",
        system_prompt=EXPLORE_SYSTEM_PROMPT,
        tools=["FileRead", "Glob", "Grep", "Bash"],
        source="built-in",
    ),
    "plan": AgentDefinition(
        name="Plan",
        description="Software architect agent for designing implementation plans. Use when you need to plan the implementation strategy for a task. Returns step-by-step plans, identifies critical files, and considers architectural trade-offs.",
        agent_type="built-in",
        system_prompt=PLAN_SYSTEM_PROMPT,
        tools=["FileRead", "Glob", "Grep", "Agent"],
        source="built-in",
    ),
    "general-purpose": AgentDefinition(
        name="general-purpose",
        description="General-purpose agent for researching complex questions, searching for code, and executing multi-step tasks.",
        agent_type="built-in",
        system_prompt=GENERAL_PURPOSE_PROMPT,
        tools=None,  # all tools inherited
        source="built-in",
    ),
}


# ── User agent loading ──

def load_user_agents(cwd: str | None = None) -> dict[str, AgentDefinition]:
    """Load user-defined agents from .myagent/agents/*.md."""
    import os
    base = Path(cwd or os.getenv("AGENT_CWD", "."))
    agents_dir = base / ".myagent" / "agents"
    if not agents_dir.is_dir():
        return {}

    result: dict[str, AgentDefinition] = {}
    for md_file in sorted(agents_dir.glob("*.md")):
        definition = _parse_agent_md(md_file)
        if definition:
            result[definition.name] = definition
    return result


def _parse_agent_md(path: Path) -> AgentDefinition | None:
    """Parse a .myagent/agents/*.md file with YAML frontmatter."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None

    parts = text.split("---", 2)
    if len(parts) < 3:
        return None

    try:
        import yaml
        meta = yaml.safe_load(parts[1]) or {}
    except Exception:
        return None

    body = parts[2].strip()
    name = meta.get("name", path.stem)
    return AgentDefinition(
        name=name,
        description=meta.get("description", ""),
        agent_type="user",
        system_prompt=body,
        provider=meta.get("provider"),
        model=meta.get("model"),
        tools=meta.get("tools"),
        disallowed_tools=meta.get("disallowedTools"),
        source=str(path),
        base_dir=str(path.parent),
    )


# ── Resolution ──

def resolve_agent(name: str, user_agents: dict[str, AgentDefinition] | None = None) -> AgentDefinition | None:
    """Resolve an agent by name: built-in first, then user agents. Case-insensitive."""
    name_lower = name.lower()
    for key, defn in BUILTIN_AGENTS.items():
        if key == name_lower:
            return defn

    if user_agents:
        for key, defn in user_agents.items():
            if key.lower() == name_lower:
                return defn

    return None


def list_all_agents(user_agents: dict[str, AgentDefinition] | None = None) -> list[AgentDefinition]:
    """Return all available agent definitions (built-in + user)."""
    agents = list(BUILTIN_AGENTS.values())
    if user_agents:
        agents.extend(user_agents.values())
    return agents
