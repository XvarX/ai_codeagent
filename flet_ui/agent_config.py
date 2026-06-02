"""Agent preset configuration for the config dialog."""

import flet as ft
from agent_definitions import BUILTIN_AGENTS

ALL_TOOL_NAMES = ["Bash", "FileRead", "FileEdit", "FileWrite", "Glob", "Grep", "Agent", "Skill"]


def build_agent_presets_section(current_config: dict) -> ft.Column:
    """Build the Agent presets configuration UI section."""
    presets = current_config.get("agent_presets", {})

    rows = []
    for agent_key, definition in BUILTIN_AGENTS.items():
        if agent_key == "general-purpose":
            continue

        preset = presets.get(agent_key, {})
        saved_provider = preset.get("provider", "")
        saved_tools = preset.get("allowed_tools", definition.tools or [])

        all_providers = set(["anthropic", "openai", "glm", "deepseek"])
        all_providers.update(current_config.get("provider_types", {}).keys())
        provider_options = [ft.dropdown.Option("", "继承默认")]
        provider_options += [ft.dropdown.Option(p, p.title()) for p in sorted(all_providers)]

        provider_dd = ft.Dropdown(
            value=saved_provider,
            options=provider_options,
            text_style=ft.TextStyle(size=12),
            border_color="#E2E6EC",
            width=140,
            data={"agent_key": agent_key, "field": "provider"},
        )

        tool_checks = []
        for tool_name in ALL_TOOL_NAMES:
            checked = tool_name in saved_tools
            tool_checks.append(
                ft.Checkbox(
                    label=tool_name,
                    value=checked,
                    label_style=ft.TextStyle(size=11),
                    data={
                        "agent_key": agent_key,
                        "field": "tool",
                        "tool_name": tool_name,
                    },
                )
            )

        rows.append(
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Text(definition.name, size=13,
                                weight=ft.FontWeight.W_600, color="#1E1B3A"),
                        ft.Text("Provider:", size=11, color="#64748B"),
                        provider_dd,
                    ], spacing=8,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Text("可用工具:", size=11, color="#64748B"),
                    ft.Row(tool_checks, spacing=4, wrap=True, run_spacing=0),
                ], spacing=4, tight=True),
                padding=ft.Padding(12, 8, 12, 8),
                border=ft.Border.all(1, "#EEF0F4"),
                border_radius=8,
                margin=ft.Margin(0, 4, 0, 4),
            )
        )

    return ft.Column(rows, spacing=4, tight=True)


def collect_agent_presets(controls: list) -> dict:
    """Collect agent preset values from UI controls."""
    presets: dict[str, dict] = {}
    for control in controls:
        _walk_and_collect(control, presets)
    return presets


def _walk_and_collect(control, presets: dict):
    data = getattr(control, "data", None)
    if isinstance(data, dict):
        agent_key = data.get("agent_key")
        if agent_key:
            if agent_key not in presets:
                presets[agent_key] = {"provider": "", "allowed_tools": []}
            field = data.get("field")
            value = getattr(control, "value", None)
            if field == "provider":
                presets[agent_key]["provider"] = value or ""
            elif field == "tool":
                tool_name = data.get("tool_name", "")
                tools_list = presets[agent_key]["allowed_tools"]
                if value and tool_name not in tools_list:
                    tools_list.append(tool_name)
                elif not value and tool_name in tools_list:
                    tools_list.remove(tool_name)

    if hasattr(control, "controls"):
        for child in control.controls:
            _walk_and_collect(child, presets)
