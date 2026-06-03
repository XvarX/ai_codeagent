"""Tests for agent definitions."""
import tempfile
from pathlib import Path
from agentcore.agent_definitions import (
    AgentDefinition, BUILTIN_AGENTS, resolve_agent,
    load_user_agents, _parse_agent_md,
)


def test_builtin_agents_exist():
    assert "explore" in BUILTIN_AGENTS
    assert "plan" in BUILTIN_AGENTS
    assert "general-purpose" in BUILTIN_AGENTS


def test_resolve_builtin():
    d = resolve_agent("Explore")
    assert d is not None
    assert d.name == "Explore"


def test_resolve_case_insensitive():
    d = resolve_agent("explore")
    assert d is not None
    assert d.name == "Explore"


def test_resolve_missing():
    assert resolve_agent("nonexistent") is None


def test_parse_agent_md():
    content = """---
name: test-agent
description: A test agent
provider: glm
tools: [FileRead, Grep]
---
You are a test agent. Do test things.
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(content)
        f.flush()
        d = _parse_agent_md(Path(f.name))
    Path(f.name).unlink()

    assert d is not None
    assert d.name == "test-agent"
    assert d.description == "A test agent"
    assert d.provider == "glm"
    assert d.tools == ["FileRead", "Grep"]
    assert "You are a test agent" in d.system_prompt


def test_resolve_user_agent():
    custom = {"my-agent": AgentDefinition(
        name="my-agent", description="x", agent_type="user",
        system_prompt="hello", provider="openai",
    )}
    d = resolve_agent("my-agent", custom)
    assert d is not None
    assert d.name == "my-agent"
    assert d.provider == "openai"


def test_general_purpose_has_all_tools():
    d = BUILTIN_AGENTS["general-purpose"]
    assert d.tools is None  # None means all tools


def test_explore_is_readonly():
    d = BUILTIN_AGENTS["explore"]
    assert "FileRead" in d.tools
    assert "FileWrite" not in d.tools
    assert "FileEdit" not in d.tools
