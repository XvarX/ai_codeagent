"""End-to-end tests for subagent system."""
import pytest
from agentcore.config import AgentConfig
from agentcore.agent_definitions import (
    BUILTIN_AGENTS, resolve_agent, list_all_agents, AgentDefinition,
)
from agentcore.controller import EventHandler


class TestHandler(EventHandler):
    """Captures done events for verification."""
    def __init__(self):
        super().__init__()
        self.done_events = []
        self.subagent_done_events = []

    async def on_subagent_done(self, agent_id: str, status: str, result: str):
        self.subagent_done_events.append({
            "agent_id": agent_id, "status": status, "result": result,
        })


def test_resolve_explore_agent():
    d = resolve_agent("explore")
    assert d is not None
    assert d.name == "Explore"
    assert d.tools is not None
    assert "FileRead" in d.tools


def test_resolve_plan_agent():
    d = resolve_agent("plan")
    assert d is not None
    assert d.name == "Plan"
    assert "Agent" in d.tools  # Plan can spawn agents too


def test_general_purpose_has_all_tools():
    d = resolve_agent("general-purpose")
    assert d is not None
    assert d.tools is None  # None = inherit all


def test_subagent_manager_creates_master(monkeypatch):
    """Test AgentManager with mocked provider creation."""
    from agentcore.subagent_manager import AgentManager

    # Mock _build_provider to avoid needing API keys
    def mock_build_provider(config):
        from unittest.mock import MagicMock
        m = MagicMock()
        m.model = "test-model"
        return m

    monkeypatch.setattr("agentcore.subagent_manager._build_provider", mock_build_provider)
    monkeypatch.setattr("agentcore.controller._build_provider", mock_build_provider)

    config = AgentConfig(provider="glm")
    mgr = AgentManager(config)

    assert "master" in mgr.agents
    assert mgr.active_id == "master"
    master = mgr.get_active()
    assert master.name == "Master"
    assert master.status == "idle"


def test_list_all_agents():
    agents = list_all_agents()
    names = {a.name for a in agents}
    assert "Explore" in names
    assert "Plan" in names
    assert "general-purpose" in names


def test_agent_definition_fields():
    d = AgentDefinition(name="test")
    assert d.tools is None
    assert d.provider is None
    assert d.agent_type == "built-in"


def test_config_agent_presets():
    config = AgentConfig(agent_presets={
        "explore": {"provider": "glm", "allowed_tools": ["FileRead", "Grep"]},
    })
    assert "explore" in config.agent_presets
    assert config.agent_presets["explore"]["provider"] == "glm"
    assert "FileRead" in config.agent_presets["explore"]["allowed_tools"]


def test_agent_tool_import():
    from agentcore.tools.agent_tool import AgentTool
    assert AgentTool.__name__ == "AgentTool"


def test_send_message_tool_import():
    from agentcore.tools.send_message_tool import SendMessageTool
    assert SendMessageTool.__name__ == "SendMessageTool"


def test_agent_sidebar_import():
    from agentcore.flet_ui.agent_sidebar import AgentSidebar
    assert AgentSidebar.__name__ == "AgentSidebar"
