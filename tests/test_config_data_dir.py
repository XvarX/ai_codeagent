"""Unit tests for data_dir support in agentcore/config.py.

Covers:
  1. Backward compatibility — from_yaml() without data_dir still works
  2. data_dir path resolution — reads from data_dir/config.yaml
  3. Auto-generate config — creates config.yaml with defaults when missing
  4. Two-level config merge — project .myagent/config.yaml overrides global
  5. data_dir preserved on returned AgentConfig
  6. get_agent_provider_config uses data_dir
"""

import os
import tempfile
from pathlib import Path

import yaml
import pytest

from agentcore.config import AgentConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_yaml(path: Path, data: dict) -> None:
    """Write a YAML file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


def _read_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ---------------------------------------------------------------------------
# 1. Backward compatibility — no data_dir, reads from cwd config.yaml
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """from_yaml() without data_dir should still work with a cwd config.yaml."""

    def test_reads_cwd_config(self, monkeypatch, tmp_path):
        """Without data_dir, config is read from the cwd config.yaml."""
        cfg_data = {
            "provider": "openai",
            "model": "gpt-4o",
            "max_turns": 30,
        }
        _write_yaml(tmp_path / "config.yaml", cfg_data)

        # Point cwd into the temp dir so from_yaml finds config.yaml there
        monkeypatch.chdir(tmp_path)

        config = AgentConfig.from_yaml()
        assert config.provider == "openai"
        assert config.model == "gpt-4o"
        assert config.max_turns == 30
        assert config.data_dir is None

    def test_default_values_without_config(self, monkeypatch, tmp_path):
        """Without any config file, defaults are used."""
        monkeypatch.chdir(tmp_path)
        # Clear relevant env vars so they don't interfere
        for var in ("AGENT_PROVIDER", "AGENT_MODEL", "AGENT_API_KEY",
                     "AGENT_BASE_URL", "AGENT_MAX_TURNS", "AGENT_MAX_MESSAGES"):
            monkeypatch.delenv(var, raising=False)

        config = AgentConfig.from_yaml()
        assert config.provider == "anthropic"
        assert config.max_turns == 50
        assert config.max_messages == 200


# ---------------------------------------------------------------------------
# 2. data_dir path resolution — reads from data_dir/config.yaml
# ---------------------------------------------------------------------------

class TestDataDirPathResolution:

    def test_reads_from_data_dir(self, tmp_path):
        """from_yaml(data_dir=...) reads config.yaml from that directory."""
        data_dir = tmp_path / "my-data-dir"
        data_dir.mkdir()
        cfg_data = {
            "provider": "glm",
            "model": "glm-4-plus",
            "max_turns": 42,
        }
        _write_yaml(data_dir / "config.yaml", cfg_data)

        config = AgentConfig.from_yaml(data_dir=str(data_dir))
        assert config.provider == "glm"
        assert config.model == "glm-4-plus"
        assert config.max_turns == 42

    def test_data_dir_takes_precedence_over_cwd(self, monkeypatch, tmp_path):
        """data_dir config should be used even if a config.yaml exists in cwd."""
        # cwd has an anthropic config
        cwd_cfg = {"provider": "anthropic", "model": "claude-sonnet-4-6-20250514"}
        _write_yaml(tmp_path / "config.yaml", cwd_cfg)
        monkeypatch.chdir(tmp_path)

        # data_dir has a deepseek config
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        data_cfg = {"provider": "deepseek", "model": "deepseek-chat"}
        _write_yaml(data_dir / "config.yaml", data_cfg)

        config = AgentConfig.from_yaml(data_dir=str(data_dir))
        assert config.provider == "deepseek"
        assert config.model == "deepseek-chat"


# ---------------------------------------------------------------------------
# 3. Auto-generate config — creates config.yaml with defaults when missing
# ---------------------------------------------------------------------------

class TestAutoGenerateConfig:

    def test_creates_config_in_data_dir(self, monkeypatch, tmp_path):
        """When config.yaml doesn't exist in data_dir, one is generated."""
        # Chdir to tmp_path so no config.example.yaml is found in cwd
        monkeypatch.chdir(tmp_path)

        data_dir = tmp_path / "new-data-dir"
        data_dir.mkdir()
        config_path = data_dir / "config.yaml"

        assert not config_path.exists()

        config = AgentConfig.from_yaml(data_dir=str(data_dir))

        # The file should now exist with default values
        assert config_path.exists()
        written = _read_yaml(config_path)
        assert written["provider"] == "anthropic"
        assert written["max_turns"] == 50

        # Returned config should use defaults
        assert config.provider == "anthropic"
        assert config.max_turns == 50

    def test_auto_generate_creates_parent_dirs(self, monkeypatch, tmp_path):
        """Auto-generate should create intermediate directories."""
        monkeypatch.chdir(tmp_path)

        data_dir = tmp_path / "nested" / "deep" / "data"
        # data_dir itself doesn't exist yet, but config_path.parent.mkdir is called
        config = AgentConfig.from_yaml(data_dir=str(data_dir))
        assert (data_dir / "config.yaml").exists()


# ---------------------------------------------------------------------------
# 4. Two-level config merge — project-level .myagent/config.yaml overrides
# ---------------------------------------------------------------------------

class TestTwoLevelConfigMerge:

    def test_project_overrides_global(self, tmp_path):
        """Project .myagent/config.yaml values override global (data_dir) config."""
        # Global config in data_dir
        data_dir = tmp_path / "global-data"
        data_dir.mkdir()
        global_cfg = {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6-20250514",
            "max_turns": 50,
        }
        _write_yaml(data_dir / "config.yaml", global_cfg)

        # Project-level override
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        project_cfg = {
            "provider": "openai",
            "model": "gpt-4o",
        }
        _write_yaml(project_dir / ".myagent" / "config.yaml", project_cfg)

        # Set cwd in global config so two-level merge can find project config
        global_cfg["cwd"] = str(project_dir)
        _write_yaml(data_dir / "config.yaml", global_cfg)

        config = AgentConfig.from_yaml(data_dir=str(data_dir))
        assert config.provider == "openai"
        assert config.model == "gpt-4o"
        # max_turns stays from global
        assert config.max_turns == 50

    def test_project_cwd_from_env(self, monkeypatch, tmp_path):
        """AGENT_CWD env var is used to locate the project config for merging."""
        data_dir = tmp_path / "global-data"
        data_dir.mkdir()
        global_cfg = {"provider": "anthropic"}
        _write_yaml(data_dir / "config.yaml", global_cfg)

        project_dir = tmp_path / "env-project"
        project_dir.mkdir()
        project_cfg = {"provider": "glm", "model": "glm-4"}
        _write_yaml(project_dir / ".myagent" / "config.yaml", project_cfg)

        monkeypatch.setenv("AGENT_CWD", str(project_dir))

        config = AgentConfig.from_yaml(data_dir=str(data_dir))
        assert config.provider == "glm"
        assert config.model == "glm-4"

    def test_project_partial_override(self, tmp_path):
        """Project config can override individual keys like api_keys."""
        data_dir = tmp_path / "global-data"
        data_dir.mkdir()
        global_cfg = {
            "provider": "anthropic",
            "api_keys": {"anthropic": "sk-global-key"},
        }
        _write_yaml(data_dir / "config.yaml", global_cfg)

        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        project_cfg = {
            "api_keys": {"anthropic": "sk-project-key"},
        }
        _write_yaml(project_dir / ".myagent" / "config.yaml", project_cfg)

        global_cfg["cwd"] = str(project_dir)
        _write_yaml(data_dir / "config.yaml", global_cfg)

        config = AgentConfig.from_yaml(data_dir=str(data_dir))
        assert config.api_key == "sk-project-key"

    def test_no_project_merge_without_data_dir(self, monkeypatch, tmp_path):
        """Two-level merge only applies when data_dir is set."""
        cwd_cfg = {"provider": "openai"}
        _write_yaml(tmp_path / "config.yaml", cwd_cfg)
        monkeypatch.chdir(tmp_path)

        # Create a project .myagent/config.yaml — should NOT be merged
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _write_yaml(project_dir / ".myagent" / "config.yaml", {"provider": "glm"})
        monkeypatch.setenv("AGENT_CWD", str(project_dir))

        config = AgentConfig.from_yaml()
        assert config.provider == "openai"


# ---------------------------------------------------------------------------
# 5. data_dir preserved on returned AgentConfig
# ---------------------------------------------------------------------------

class TestDataDirPreserved:

    def test_data_dir_set_on_config(self, tmp_path):
        """Returned AgentConfig.data_dir matches the argument."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_yaml(data_dir / "config.yaml", {"provider": "anthropic"})

        config = AgentConfig.from_yaml(data_dir=str(data_dir))
        assert config.data_dir == str(data_dir)

    def test_data_dir_none_by_default(self, monkeypatch, tmp_path):
        """Without data_dir argument, config.data_dir is None."""
        monkeypatch.chdir(tmp_path)
        _write_yaml(tmp_path / "config.yaml", {"provider": "anthropic"})

        config = AgentConfig.from_yaml()
        assert config.data_dir is None

    def test_explicit_path_and_data_dir(self, tmp_path):
        """Explicit path takes precedence; data_dir is still preserved."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        other_dir = tmp_path / "other"
        other_dir.mkdir()

        _write_yaml(other_dir / "custom.yaml", {
            "provider": "deepseek",
            "model": "deepseek-coder",
        })

        config = AgentConfig.from_yaml(
            path=str(other_dir / "custom.yaml"),
            data_dir=str(data_dir),
        )
        # Reads from the explicit path
        assert config.provider == "deepseek"
        assert config.model == "deepseek-coder"
        # data_dir is still recorded
        assert config.data_dir == str(data_dir)


# ---------------------------------------------------------------------------
# 6. get_agent_provider_config uses data_dir
# ---------------------------------------------------------------------------

class TestGetAgentProviderConfigUsesDataDir:

    def test_reads_from_data_dir(self, tmp_path):
        """get_agent_provider_config reads config.yaml from data_dir."""
        data_dir = tmp_path / "agent-data"
        data_dir.mkdir()
        _write_yaml(data_dir / "config.yaml", {
            "provider": "anthropic",
            "agent_presets": {
                "coder": {"provider": "openai"},
            },
            "api_keys": {"openai": "sk-test-key"},
            "base_urls": {"openai": "https://api.openai.com/v1"},
            "models": {"openai": "gpt-4o"},
        })

        config = AgentConfig.from_yaml(data_dir=str(data_dir))
        result = config.get_agent_provider_config("coder")

        assert result is not None
        assert result["provider"] == "openai"
        assert result["api_key"] == "sk-test-key"
        assert result["base_url"] == "https://api.openai.com/v1"
        assert result["model"] == "gpt-4o"

    def test_reads_from_cwd_without_data_dir(self, monkeypatch, tmp_path):
        """Without data_dir, reads from cwd config.yaml."""
        _write_yaml(tmp_path / "config.yaml", {
            "provider": "anthropic",
            "agent_presets": {
                "reviewer": {"provider": "glm"},
            },
            "api_keys": {"glm": "glm-test-key"},
            "base_urls": {"glm": "https://glm.api"},
            "models": {"glm": "glm-4"},
        })
        monkeypatch.chdir(tmp_path)

        config = AgentConfig.from_yaml()
        result = config.get_agent_provider_config("reviewer")

        assert result is not None
        assert result["provider"] == "glm"
        assert result["api_key"] == "glm-test-key"

    def test_returns_none_for_unknown_preset(self, tmp_path):
        """Unknown preset returns None."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_yaml(data_dir / "config.yaml", {"provider": "anthropic"})

        config = AgentConfig.from_yaml(data_dir=str(data_dir))
        assert config.get_agent_provider_config("nonexistent") is None

    def test_returns_none_when_no_provider_in_preset(self, tmp_path):
        """Preset without a provider key returns None."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        _write_yaml(data_dir / "config.yaml", {
            "provider": "anthropic",
            "agent_presets": {"empty": {"allowed_tools": ["bash"]}},
        })

        config = AgentConfig.from_yaml(data_dir=str(data_dir))
        assert config.get_agent_provider_config("empty") is None

    def test_data_dir_isolation(self, monkeypatch, tmp_path):
        """get_agent_provider_config reads from data_dir, not cwd."""
        # cwd has glm preset
        monkeypatch.chdir(tmp_path)
        _write_yaml(tmp_path / "config.yaml", {
            "provider": "anthropic",
            "agent_presets": {"coder": {"provider": "glm"}},
            "api_keys": {"glm": "glm-from-cwd"},
        })

        # data_dir has openai preset
        data_dir = tmp_path / "isolated"
        data_dir.mkdir()
        _write_yaml(data_dir / "config.yaml", {
            "provider": "anthropic",
            "agent_presets": {"coder": {"provider": "openai"}},
            "api_keys": {"openai": "sk-from-data-dir"},
        })

        config = AgentConfig.from_yaml(data_dir=str(data_dir))
        result = config.get_agent_provider_config("coder")

        assert result["provider"] == "openai"
        assert result["api_key"] == "sk-from-data-dir"
