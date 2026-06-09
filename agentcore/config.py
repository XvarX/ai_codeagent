"""Configuration management for the agent framework.

Supports:
  1. config.yaml next to the exe (PyInstaller) or in project dir
  2. config.example.yaml as fallback
  3. Environment variables (override)
"""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AgentConfig:
    """Agent configuration — provider, model, tools, limits."""

    provider: str = "anthropic"
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    cwd: str | None = None
    max_turns: int = 50
    max_messages: int = 200
    verbose: bool = False
    context_window: int = 128000
    compact_threshold: float = 0.85
    reserved_output: int = 8000
    agent_presets: dict = field(default_factory=dict)
    data_dir: str | None = None  # .ai-code-agent/ directory absolute path

    @classmethod
    def from_yaml(cls, path: str | None = None, data_dir: str | None = None) -> "AgentConfig":
        """Load configuration from a YAML file, with env vars as override."""
        import yaml

        cfg: dict = {}

        # Find config file: explicit path > data_dir > next to exe (PyInstaller) > cwd > example
        if path:
            config_path = Path(path)
        elif data_dir:
            # New path: .ai-code-agent/config.yaml
            config_path = Path(data_dir) / "config.yaml"
        else:
            # Legacy: PyInstaller exe dir or cwd
            if getattr(sys, 'frozen', False):
                exe_dir = Path(sys.executable).parent
                config_path = exe_dir / "config.yaml"
                if not config_path.exists():
                    meipass = getattr(sys, '_MEIPASS', '')
                    if meipass:
                        meipass_path = Path(meipass) / "config.yaml"
                        if meipass_path.exists():
                            config_path = meipass_path
            else:
                config_path = Path("config.yaml")
        if not config_path.exists():
            # Initialize config at target path from example or defaults
            example = Path("config.example.yaml")
            if example.exists():
                with open(example, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
            else:
                cfg = {
                    "provider": "anthropic",
                    "model": "claude-sonnet-4-6-20250514",
                    "max_turns": 50,
                    "max_messages": 200,
                    "verbose": False,
                    "api_keys": {},
                    "base_urls": {},
                    "models": {},
                    "context_windows": {},
                    "compact_thresholds": {},
                    "reserved_outputs": {},
                }
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}

        # Two-level config merge: project-level .myagent/config.yaml overrides global
        if data_dir:
            project_cwd = os.environ.get("AGENT_CWD") or cfg.get("cwd")
            if project_cwd:
                project_config = Path(project_cwd) / ".myagent" / "config.yaml"
                if project_config.exists():
                    with open(project_config, "r", encoding="utf-8") as f:
                        project_cfg = yaml.safe_load(f) or {}
                    for key in ("provider", "model", "api_key", "api_keys",
                                "base_url", "base_urls", "models",
                                "context_window", "context_windows",
                                "compact_threshold", "compact_thresholds",
                                "reserved_output", "reserved_outputs"):
                        if key in project_cfg:
                            cfg[key] = project_cfg[key]

        # Provider
        provider = (
            os.environ.get("AGENT_PROVIDER")
            or cfg.get("provider")
            or "anthropic"
        )

        # API key: env > yaml api_key > yaml api_keys[provider] > env PROVIDER_API_KEY
        api_key = os.environ.get("AGENT_API_KEY") or cfg.get("api_key")
        if not api_key:
            api_key = cfg.get("api_keys", {}).get(provider, "")
        if not api_key:
            provider_env_keys = {
                "anthropic": "ANTHROPIC_API_KEY",
                "openai": "OPENAI_API_KEY",
                "glm": "GLM_API_KEY",
                "deepseek": "DEEPSEEK_API_KEY",
            }
            api_key = os.environ.get(provider_env_keys.get(provider, "")) or ""

        # Base URL: env > yaml base_url > yaml base_urls[provider]
        base_url = os.environ.get("AGENT_BASE_URL") or cfg.get("base_url")
        if not base_url:
            base_url = cfg.get("base_urls", {}).get(provider, "")

        # Per-provider defaults for context settings
        DEFAULT_CONTEXTS = {
            "anthropic": 200000, "openai": 128000,
            "glm": 128000, "deepseek": 64000,
        }

        context_window = int(
            os.environ.get("AGENT_CONTEXT_WINDOW")
            or cfg.get("context_window")
            or cfg.get("context_windows", {}).get(provider)
            or DEFAULT_CONTEXTS.get(provider, 128000)
        )
        compact_threshold = float(
            os.environ.get("AGENT_COMPACT_THRESHOLD")
            or cfg.get("compact_threshold")
            or cfg.get("compact_thresholds", {}).get(provider)
            or 0.85
        )
        reserved_output = int(
            os.environ.get("AGENT_RESERVED_OUTPUT")
            or cfg.get("reserved_output")
            or cfg.get("reserved_outputs", {}).get(provider)
            or 8000
        )

        agent_presets = cfg.get("agent_presets", {})
        normalized_presets = {}
        for pname, pdata in agent_presets.items():
            normalized_presets[pname] = {
                "provider": pdata.get("provider", ""),
                "allowed_tools": pdata.get("allowed_tools", []),
            }

        return cls(
            provider=provider,
            model=os.environ.get("AGENT_MODEL") or cfg.get("model"),
            api_key=api_key or None,
            base_url=base_url or None,
            cwd=os.environ.get("AGENT_CWD") or cfg.get("cwd"),
            max_turns=int(os.environ.get("AGENT_MAX_TURNS") or cfg.get("max_turns", 50)),
            max_messages=int(os.environ.get("AGENT_MAX_MESSAGES") or cfg.get("max_messages", 200)),
            verbose=bool(
                os.environ.get("AGENT_VERBOSE")
                or cfg.get("verbose", False)
            ),
            context_window=context_window,
            compact_threshold=compact_threshold,
            reserved_output=reserved_output,
            agent_presets=normalized_presets,
            data_dir=data_dir,
        )

    def get_agent_provider_config(self, preset_name: str) -> dict | None:
        """Get provider config for a named agent preset.

        Returns {provider, api_key, base_url, model} or None for defaults.
        """
        preset = self.agent_presets.get(preset_name.lower())
        if not preset or not preset.get("provider"):
            return None

        provider = preset["provider"]
        import yaml
        if self.data_dir:
            config_path = Path(self.data_dir) / "config.yaml"
        else:
            config_path = Path("config.yaml")
        cfg = {}
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}

        return {
            "provider": provider,
            "api_key": cfg.get("api_keys", {}).get(provider, ""),
            "base_url": cfg.get("base_urls", {}).get(provider, ""),
            "model": cfg.get("models", {}).get(provider, ""),
        }

    # Keep from_env for backwards compat
    @classmethod
    def from_env(cls, provider: str | None = None) -> "AgentConfig":
        return cls.from_yaml()
