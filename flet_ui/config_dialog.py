"""LLM Provider configuration dialog."""

import flet as ft
import yaml
from pathlib import Path


CONFIG_PATH = Path("config.yaml")

PROVIDER_OPTIONS = [
    ft.dropdown.Option("anthropic", "Anthropic"),
    ft.dropdown.Option("openai", "OpenAI"),
    ft.dropdown.Option("glm", "GLM"),
    ft.dropdown.Option("deepseek", "DeepSeek"),
]


def show_config_dialog(page: ft.Page, on_save=None):
    """Open the LLM configuration dialog."""

    config = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    provider = config.get("provider", "glm")
    api_key = config.get("api_key") or config.get("api_keys", {}).get(provider, "")
    model = config.get("model", "")
    base_url = config.get("base_url") or config.get("base_urls", {}).get(provider, "")

    provider_dd = ft.Dropdown(
        value=provider,
        options=PROVIDER_OPTIONS,
        text_style=ft.TextStyle(size=12),
        border_color="#E2E6EC",
    )

    api_key_field = ft.TextField(
        value=api_key,
        hint_text="API Key",
        hint_style=ft.TextStyle(size=12, color="#94A3B8"),
        text_style=ft.TextStyle(size=12),
        password=True,
        can_reveal_password=True,
        border=ft.InputBorder.UNDERLINE,
    )
    model_field = ft.TextField(
        value=model,
        hint_text="Model (e.g. glm-5.1)",
        hint_style=ft.TextStyle(size=12, color="#94A3B8"),
        text_style=ft.TextStyle(size=12),
        border=ft.InputBorder.UNDERLINE,
    )
    base_url_field = ft.TextField(
        value=base_url,
        hint_text="Base URL (optional)",
        hint_style=ft.TextStyle(size=12, color="#94A3B8"),
        text_style=ft.TextStyle(size=12),
        border=ft.InputBorder.UNDERLINE,
    )

    status_text = ft.Text("", size=10, color="#EF4444")

    def on_provider_select(e):
        new_provider = provider_dd.value
        api_key_field.value = config.get("api_keys", {}).get(new_provider, "")
        base_url_field.value = config.get("base_urls", {}).get(new_provider, "")
        page.update()

    provider_dd.on_select = on_provider_select

    def save_click(e):
        # Merge into existing config to preserve nested structure
        config["provider"] = provider_dd.value
        config["model"] = model_field.value or None
        config.setdefault("api_keys", {})[provider_dd.value] = api_key_field.value
        config.setdefault("base_urls", {})[provider_dd.value] = base_url_field.value
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
        title=ft.Text("LLM 配置", size=14, weight=ft.FontWeight.W_600),
        content=ft.Column([
            ft.Text("Provider", size=11, color="#475569"),
            provider_dd,
            ft.Container(height=12),
            api_key_field,
            ft.Container(height=12),
            model_field,
            ft.Container(height=12),
            base_url_field,
            ft.Container(height=6),
            status_text,
        ], width=400),
        actions=[
            ft.TextButton(content=ft.Text("取消", color="#64748B"), on_click=lambda e: page.pop_dialog()),
            ft.TextButton(content=ft.Text("保存", color="#6366F1"), on_click=save_click),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
        shape=ft.RoundedRectangleBorder(radius=10),
    )

    page.show_dialog(dlg)
