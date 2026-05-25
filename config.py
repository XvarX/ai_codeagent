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

    @classmethod
    def from_yaml(cls, path: str | None = None) -> "AgentConfig":
        """Load configuration from a YAML file, with env vars as override."""
        import yaml

        cfg: dict = {}

        # Find config file: next to exe (PyInstaller) > cwd > example
        if path:
            config_path = Path(path)
        else:
            # PyInstaller: look next to exe first
            if getattr(sys, 'frozen', False):
                exe_dir = Path(sys.executable).parent
                config_path = exe_dir / "config.yaml"
            else:
                config_path = Path("config.yaml")
        if not config_path.exists():
            example = Path("config.example.yaml")
            if example.exists():
                config_path = example
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}

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
            context_window=int(
                os.environ.get("AGENT_CONTEXT_WINDOW") or cfg.get("context_window", 128000)
            ),
            compact_threshold=float(
                os.environ.get("AGENT_COMPACT_THRESHOLD") or cfg.get("compact_threshold", 0.85)
            ),
            reserved_output=int(
                os.environ.get("AGENT_RESERVED_OUTPUT") or cfg.get("reserved_output", 8000)
            ),
        )

    # Keep from_env for backwards compat
    @classmethod
    def from_env(cls, provider: str | None = None) -> "AgentConfig":
        return cls.from_yaml()
