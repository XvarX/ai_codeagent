"""LLM Provider configuration dialog."""

import flet as ft
import yaml
from pathlib import Path


CONFIG_PATH = Path("config.yaml")

BUILTIN_PROVIDERS = ["anthropic", "openai", "glm", "deepseek"]


def show_config_dialog(page: ft.Page, on_save=None):
    """Open the LLM configuration dialog."""

    config = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    provider = config.get("provider", "glm")
    api_key = config.get("api_key") or config.get("api_keys", {}).get(provider, "")
    model = config.get("models", {}).get(provider, "") or config.get("model", "")
    base_url = config.get("base_url") or config.get("base_urls", {}).get(provider, "")
    context_window = str(
        config.get("context_window")
        or config.get("context_windows", {}).get(provider, 128000)
    )
    compact_threshold = str(
        config.get("compact_threshold")
        or config.get("compact_thresholds", {}).get(provider, 0.85)
    )
    reserved_output = str(
        config.get("reserved_output")
        or config.get("reserved_outputs", {}).get(provider, 8000)
    )

    DEFAULT_CONTEXTS = {"anthropic": 200000, "openai": 128000, "glm": 128000, "deepseek": 64000}
    DEFAULT_MODELS = {
        "anthropic": "claude-sonnet-4-6-20250514",
        "openai": "gpt-4o",
        "glm": "glm-5.1",
        "deepseek": "deepseek-chat",
    }

    # Build provider options from builtins + any providers found in config
    all_providers = set(BUILTIN_PROVIDERS)
    for key in ["api_keys", "base_urls", "models", "provider_types"]:
        all_providers.update(config.get(key, {}).keys())
    provider_options = [
        ft.dropdown.Option(p, p.title()) for p in sorted(all_providers)
    ]

    provider_dd = ft.Dropdown(
        value=provider if provider in all_providers else sorted(all_providers)[0],
        options=provider_options,
        text_style=ft.TextStyle(size=14),
        border_color="#E2E6EC",
    )

    api_key_field = ft.TextField(
        value=api_key,
        hint_text="API Key",
        hint_style=ft.TextStyle(size=14, color="#94A3B8"),
        text_style=ft.TextStyle(size=14),
        password=True,
        can_reveal_password=True,
        border=ft.InputBorder.UNDERLINE,
    )
    model_field = ft.TextField(
        value=model,
        hint_text="Model (e.g. glm-5.1)",
        hint_style=ft.TextStyle(size=14, color="#94A3B8"),
        text_style=ft.TextStyle(size=14),
        border=ft.InputBorder.UNDERLINE,
    )
    base_url_field = ft.TextField(
        value=base_url,
        hint_text="Base URL (optional)",
        hint_style=ft.TextStyle(size=14, color="#94A3B8"),
        text_style=ft.TextStyle(size=14),
        border=ft.InputBorder.UNDERLINE,
    )
    context_window_field = ft.TextField(
        value=context_window,
        hint_text="Context Window (tokens)",
        hint_style=ft.TextStyle(size=14, color="#94A3B8"),
        text_style=ft.TextStyle(size=14),
        border=ft.InputBorder.UNDERLINE,
        keyboard_type=ft.KeyboardType.NUMBER,
    )
    compact_threshold_field = ft.TextField(
        value=compact_threshold,
        hint_text="Compact Threshold (0.1 - 1.0)",
        hint_style=ft.TextStyle(size=14, color="#94A3B8"),
        text_style=ft.TextStyle(size=14),
        border=ft.InputBorder.UNDERLINE,
    )
    reserved_output_field = ft.TextField(
        value=reserved_output,
        hint_text="Reserved Output (tokens)",
        hint_style=ft.TextStyle(size=14, color="#94A3B8"),
        text_style=ft.TextStyle(size=14),
        border=ft.InputBorder.UNDERLINE,
        keyboard_type=ft.KeyboardType.NUMBER,
    )

    status_text = ft.Text("", size=12, color="#EF4444")

    def on_provider_select(e):
        new_provider = provider_dd.value
        api_key_field.value = config.get("api_keys", {}).get(new_provider, "")
        base_url_field.value = config.get("base_urls", {}).get(new_provider, "")
        model_field.value = config.get("models", {}).get(new_provider, "") or DEFAULT_MODELS.get(new_provider, "")
        context_window_field.value = str(
            config.get("context_window")
            or config.get("context_windows", {}).get(new_provider)
            or DEFAULT_CONTEXTS.get(new_provider, 128000)
        )
        compact_threshold_field.value = str(
            config.get("compact_threshold")
            or config.get("compact_thresholds", {}).get(new_provider, 0.85)
        )
        reserved_output_field.value = str(
            config.get("reserved_output")
            or config.get("reserved_outputs", {}).get(new_provider, 8000)
        )
        page.update()

    provider_dd.on_select = on_provider_select

    new_provider_field = ft.TextField(
        hint_text="New provider name...",
        hint_style=ft.TextStyle(size=13, color="#94A3B8"),
        text_style=ft.TextStyle(size=13),
        border=ft.InputBorder.UNDERLINE,
        visible=False,
    )
    new_provider_type_dd = ft.Dropdown(
        value="openai",
        options=[
            ft.dropdown.Option("openai", "OpenAI-compatible"),
            ft.dropdown.Option("anthropic", "Anthropic-compatible"),
        ],
        text_style=ft.TextStyle(size=13),
        visible=False,
    )

    def show_add_provider(e):
        new_provider_field.visible = not new_provider_field.visible
        new_provider_type_dd.visible = new_provider_field.visible
        add_provider_row.visible = new_provider_field.visible
        new_provider_field.value = ""
        new_provider_field.update()
        new_provider_type_dd.update()
        add_provider_row.update()

    def add_provider(e):
        name = new_provider_field.value.strip().lower()
        if name:
            if name not in [o.key for o in provider_dd.options]:
                provider_dd.options.append(ft.dropdown.Option(name, name.title()))
                all_providers.add(name)
            config.setdefault("provider_types", {})[name] = new_provider_type_dd.value
            provider_dd.value = name
            on_provider_select(None)
            new_provider_field.visible = False
            new_provider_type_dd.visible = False
            add_provider_row.visible = False
            new_provider_field.value = ""
            new_provider_field.update()
            new_provider_type_dd.update()
            add_provider_row.update()
            provider_dd.update()
        page.update()

    new_provider_field.on_submit = add_provider

    add_provider_row = ft.Row([
        new_provider_field,
        new_provider_type_dd,
    ], spacing=8, visible=False)

    add_provider_btn = ft.TextButton(
        content=ft.Text("+ Add Provider", size=12, color="#6366F1"),
        on_click=show_add_provider,
    )

    def save_click(e):
        # Auto-add pending new provider before save
        pending = new_provider_field.value.strip().lower()
        if pending and pending not in [o.key for o in provider_dd.options]:
            provider_dd.options.append(ft.dropdown.Option(pending, pending.title()))
            config.setdefault("provider_types", {})[pending] = new_provider_type_dd.value
        # If a new provider was typed (even if already added), make it current
        if pending:
            config.setdefault("provider_types", {})[pending] = new_provider_type_dd.value

        # Merge into existing config to preserve nested structure
        config["provider"] = provider_dd.value
        config["model"] = model_field.value or None
        config.setdefault("models", {})[provider_dd.value] = model_field.value or None
        config.setdefault("api_keys", {})[provider_dd.value] = api_key_field.value
        config.setdefault("base_urls", {})[provider_dd.value] = base_url_field.value
        config.setdefault("context_windows", {})[provider_dd.value] = int(context_window_field.value or 128000)
        config.setdefault("compact_thresholds", {})[provider_dd.value] = float(compact_threshold_field.value or 0.85)
        config.setdefault("reserved_outputs", {})[provider_dd.value] = int(reserved_output_field.value or 8000)
        # Hide add row if still visible
        new_provider_field.visible = False
        new_provider_type_dd.visible = False
        add_provider_row.visible = False
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
            from config import AgentConfig
            updated_config = AgentConfig.from_yaml()
            if on_save:
                on_save(updated_config)
            page.pop_dialog()
        except Exception as ex:
            status_text.value = f"Save failed: {ex}"
            status_text.update()

    dlg = ft.AlertDialog(
        title=ft.Text("LLM 配置", size=16, weight=ft.FontWeight.W_600),
        content=ft.Column([
            ft.Text("Provider", size=13, color="#475569"),
            provider_dd,
            add_provider_btn,
            add_provider_row,
            ft.Container(height=14),
            api_key_field,
            ft.Container(height=14),
            model_field,
            ft.Container(height=14),
            base_url_field,
            ft.Container(height=18),
            ft.Divider(height=1, color="#EEF0F4"),
            ft.Container(height=10),
            ft.Text("上下文设置", size=13, weight=ft.FontWeight.W_600, color="#475569"),
            ft.Container(height=10),
            context_window_field,
            ft.Container(height=14),
            compact_threshold_field,
            ft.Container(height=14),
            reserved_output_field,
            ft.Container(height=8),
            status_text,
        ], width=550, height=580, scroll=ft.ScrollMode.AUTO),
        actions=[
            ft.TextButton(content=ft.Text("取消", size=14, color="#64748B"), on_click=lambda e: page.pop_dialog()),
            ft.TextButton(content=ft.Text("保存", size=14, color="#6366F1"), on_click=save_click),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        shape=ft.RoundedRectangleBorder(radius=10),
    )

    page.show_dialog(dlg)
