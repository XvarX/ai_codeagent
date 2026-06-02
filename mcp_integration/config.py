""".mcp.json config loader — mirrors src/services/mcp/config.ts."""

import json
import os
import re
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class MCPServerConfig:
    """Parsed configuration for a single MCP server."""
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


def _expand_env(value: str) -> str:
    """Expand ${VAR} placeholders in a string."""

    def replacer(m):
        return os.environ.get(m.group(1), "")

    return re.sub(r"\$\{(\w+)\}", replacer, value)


def _expand_env_in(obj):
    """Recursively expand env vars in strings."""
    if isinstance(obj, str):
        return _expand_env(obj)
    elif isinstance(obj, list):
        return [_expand_env_in(v) for v in obj]
    elif isinstance(obj, dict):
        return {k: _expand_env_in(v) for k, v in obj.items()}
    return obj


def load_mcp_configs(cwd: Path | str) -> list[MCPServerConfig]:
    """Load .mcp.json from cwd and parent directories, merge by server name.

    Closer to cwd takes priority. Returns list of validated configs.
    """
    cwd = Path(cwd).resolve()
    merged: dict[str, dict] = {}

    # Walk cwd up to root, collecting .mcp.json files
    dirs = [cwd] + list(cwd.parents)
    for d in dirs:
        config_path = d / ".mcp.json"
        if not config_path.exists():
            continue
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        servers = data.get("mcpServers", {})
        if not isinstance(servers, dict):
            continue

        # Closer directories override parent configs
        for name, raw in servers.items():
            if not isinstance(raw, dict):
                continue
            if name not in merged:
                merged[name] = raw

    # Parse and validate — reverse so closer dirs come last
    configs: list[MCPServerConfig] = []
    for name, raw in reversed(merged.items()):
        command = raw.get("command", "")
        if not command:
            continue

        args = raw.get("args", [])
        env = raw.get("env", {})
        if isinstance(args, str):
            args = [args]
        if not isinstance(env, dict):
            env = {}

        command = _expand_env(command)
        args = _expand_env_in(args)
        env = _expand_env_in(env)

        full_env = {**os.environ, **env}

        configs.append(MCPServerConfig(
            name=name,
            command=command,
            args=args if isinstance(args, list) else [],
            env=full_env,
        ))

    return configs
