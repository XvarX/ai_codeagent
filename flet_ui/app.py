"""Flet main app — assembles ChatView, InputBar, DebugDrawer, and AgentController."""

import json
from pathlib import Path
from datetime import datetime

import flet as ft

from config import AgentConfig
from controller import AgentController, EventHandler
from flet_ui.chat_view import ChatView
from flet_ui.input_bar import InputBar
from flet_ui.debug_drawer import DebugDrawer
from flet_ui.config_dialog import show_config_dialog


class _FletEventHandler(EventHandler):
    """Bridge from AgentController events to Flet UI updates."""

    def __init__(self, app: "FletApp"):
        self.app = app

    async def on_thinking(self):
        self.app._on_thinking()

    async def on_text_delta(self, token: str):
        self.app._on_text_delta(token)

    async def on_tool_use(self, name: str, input_dict: dict, tool_use_id: str = ""):
        self.app._on_tool_use(name, input_dict)

    async def on_tool_result(self, name: str, result: str, is_error: bool):
        self.app._on_tool_result(name, result, is_error)

    async def on_response_done(self, raw: dict):
        self.app._on_response_done(raw)

    async def on_done(self, final_text: str):
        self.app._on_done(final_text)

    async def on_error(self, message: str):
        self.app._on_error(message)

    async def on_compact(self, pre_tokens: int, post_tokens: int, trigger: str):
        self.app._on_compact(pre_tokens, post_tokens, trigger)


class FletApp:
    """Main Flet application controller."""

    def __init__(self, page: ft.Page, config: AgentConfig):
        self.page = page
        self.config = config

        self.handler = _FletEventHandler(self)
        self.controller = AgentController(config, self.handler)

        self.chat_view = ChatView()
        self.debug_drawer = DebugDrawer(
            on_compact=self._manual_compact,
            on_clear=self._clear_history,
        )
        self.input_bar = InputBar(on_send=self._on_send)

        self._current_assistant_bubble: ft.Container | None = None
        self._current_md_text: str = ""
        self._log_path = self._init_log()

        self._build_ui()

    def _init_log(self) -> Path:
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        log_path = logs_dir / f"agent_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        log_path.write_text("", encoding="utf-8")
        return log_path

    def _build_ui(self):
        self.page.title = "AI Code Agent"
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.window.width = 1200
        self.page.window.height = 750
        self.page.window.min_width = 800
        self.page.window.min_height = 500
        self.page.padding = 0
        self.page.bgcolor = "#FFFFFF"

        self.page.appbar = ft.AppBar(
            title=ft.Row([
                ft.Container(
                    content=ft.Text("A", size=10, color="white",
                                   weight=ft.FontWeight.W_700),
                    width=22, height=22, border_radius=5,
                    gradient=ft.LinearGradient(
                        begin=ft.alignment.top_left,
                        end=ft.alignment.bottom_right,
                        colors=["#6366F1", "#8B5CF6"],
                    ),
                    alignment=ft.alignment.center,
                ),
                ft.Text("AI Code Agent", size=14, weight=ft.FontWeight.W_600,
                        color="#1E1B3A"),
                ft.Container(
                    content=ft.Text(
                        f"{self.config.provider}  |  {self.config.model or 'default'}",
                        size=10, color="#94A3B8",
                    ),
                    bgcolor="#F1F3F6", border_radius=4,
                    padding=ft.Padding.symmetric(horizontal=7, vertical=2),
                ),
            ], spacing=10),
            actions=[
                ft.TextButton(
                    text="配置", style=ft.ButtonStyle(
                        color="#64748B", text_style=ft.TextStyle(size=11),
                    ),
                    on_click=lambda e: show_config_dialog(
                        self.page, on_save=self._on_config_saved),
                ),
                ft.TextButton(
                    text="清除", style=ft.ButtonStyle(
                        color="#64748B", text_style=ft.TextStyle(size=11),
                    ),
                    on_click=lambda e: self._clear_history(),
                ),
                ft.TextButton(
                    text="调试", style=ft.ButtonStyle(
                        color="#94A3B8", text_style=ft.TextStyle(size=11),
                    ),
                    on_click=lambda e: self.debug_drawer._toggle(),
                ),
            ],
            bgcolor="#FAFBFC",
        )

        main_row = ft.Row(
            [self.chat_view, self.debug_drawer],
            spacing=0,
        )

        self.page.add(main_row)
        self.page.add(self.input_bar)

        self.page.on_keyboard_event = self._on_keyboard

    def _on_thinking(self):
        self.chat_view.show_thinking()

    def _on_text_delta(self, token: str):
        self._current_md_text += token
        if self._current_assistant_bubble is None:
            avatar = ft.Container(
                content=ft.Text("AI", size=10, color="white",
                               weight=ft.FontWeight.W_600),
                width=28, height=28, border_radius=14,
                gradient=ft.LinearGradient(
                    begin=ft.alignment.top_left,
                    end=ft.alignment.bottom_right,
                    colors=["#6366F1", "#8B5CF6"],
                ),
                alignment=ft.alignment.center,
                shadow=ft.BoxShadow(
                    blur_radius=4,
                    color=ft.colors.with_opacity(0.25, "#6366F1"),
                    offset=ft.Offset(0, 1),
                ),
            )
            self._current_assistant_bubble = ft.Container(
                content=ft.Text(self._current_md_text, size=12, color="#1E1B3A",
                               selectable=True),
                bgcolor="#FAFBFC",
                border=ft.Border.all(1, "#EEF0F4"),
                border_radius=ft.BorderRadius.only(
                    top_left=3, top_right=15, bottom_left=15, bottom_right=15,
                ),
                padding=ft.Padding.symmetric(horizontal=15, vertical=10),
            )
            row = ft.Row(
                [avatar, self._current_assistant_bubble],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )
            self.chat_view.controls.append(row)
        else:
            self._current_assistant_bubble.content = ft.Markdown(
                self._current_md_text,
                selectable=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                code_theme="atom-one-light",
                code_style=ft.TextStyle(size=11, font_family="monospace"),
            )
        self._current_assistant_bubble.update()

    def _on_tool_use(self, name: str, input_dict: dict):
        preview = ", ".join(
            f"{k}={str(v)[:50]!r}" for k, v in input_dict.items()
        )
        self.chat_view.add_tool_label(name, preview)
        self.debug_drawer.add_event(
            "[Tool Call]", f"{name}: {preview}", "#6366F1",
        )

    def _on_tool_result(self, name: str, result: str, is_error: bool):
        color = "#EF4444" if is_error else "#10B981"
        preview = result[:300].replace("\n", " ")
        self.debug_drawer.add_event(
            "[Tool Result]",
            f"{name} ({len(result)} chars): {preview}",
            color,
        )

    def _on_response_done(self, raw: dict):
        if self._current_assistant_bubble is not None:
            self._current_assistant_bubble.content = ft.Markdown(
                self._current_md_text,
                selectable=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                code_theme="atom-one-light",
                code_style=ft.TextStyle(size=11, font_family="monospace"),
            )
            self._current_assistant_bubble.update()
        self._current_md_text = ""
        self._current_assistant_bubble = None

        orig_usage = raw.get("usage", {})
        norm_usage = self._normalize_usage(orig_usage)
        self.debug_drawer.update_context_usage(norm_usage)

        req = raw.get("_request", {})
        resp = {k: v for k, v in raw.items()
                if k not in ("_request", "_tool_use_blocks")}
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write("=" * 40 + " TURN " + "=" * 40 + "\n")
            f.write("── API Request ──\n")
            f.write(json.dumps(req, ensure_ascii=False, indent=2) + "\n\n")
            f.write("── API Response ──\n")
            f.write(json.dumps(resp, ensure_ascii=False, indent=2) + "\n")
            f.write("─" * 90 + "\n")

        msgs = req.get("messages", [])
        model = req.get("model", "?")
        prompt_tokens = norm_usage.get("prompt_tokens", "?")
        completion_tokens = norm_usage.get("completion_tokens", "?")
        self.debug_drawer.add_event(
            "[Response]", f"Model: {model}  |  Msgs: {len(msgs)}  |  "
            f"prompt={prompt_tokens}, completion={completion_tokens}",
            "#10B981",
        )

    def _on_done(self, final_text: str):
        self.chat_view.hide_thinking()
        self.input_bar.set_busy(False)

    def _on_error(self, message: str):
        self.debug_drawer.add_event("[Error]", message, "#EF4444")
        self.chat_view.hide_thinking()
        self.input_bar.set_busy(False)

    def _on_compact(self, pre_tokens: int, post_tokens: int, trigger: str):
        self.chat_view.add_tool_label(
            "Compact", f"~{pre_tokens} -> ~{post_tokens} tokens ({trigger})",
        )
        self.debug_drawer.add_event(
            "[Compact]",
            f"Trigger: {trigger}\nTokens: ~{pre_tokens} -> ~{post_tokens}",
            "#F59E0B",
        )
        self.debug_drawer.update_context_usage(
            {"prompt_tokens": post_tokens, "total_tokens": post_tokens},
        )

    def _normalize_usage(self, usage: dict) -> dict:
        if not usage:
            return {}
        if "prompt_tokens" not in usage and "input_tokens" in usage:
            input_total = (
                (usage.get("input_tokens") or 0)
                + (usage.get("cache_creation_input_tokens") or 0)
                + (usage.get("cache_read_input_tokens") or 0)
            )
            output = usage.get("output_tokens") or 0
            cache_tokens = usage.get("cache_read_input_tokens") or 0
            return {
                "prompt_tokens": input_total,
                "completion_tokens": output,
                "total_tokens": input_total + output,
                "prompt_tokens_details": {"cached_tokens": cache_tokens},
            }
        if "total_tokens" not in usage:
            usage["total_tokens"] = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
        return usage

    def _on_send(self, text: str):
        if text.strip().lower() == "/compact":
            self._manual_compact()
            return

        self.chat_view.add_user_message(text)
        self.chat_view.show_thinking()
        self.input_bar.set_busy(True)

        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write("\n" + "*" * 60 + "\n")
            f.write(f"User: {text}\n")
            f.write("*" * 60 + "\n\n")

        self.page.run_task(self.controller.send_message, text)

    def _clear_history(self):
        self.controller.clear_history()
        self.chat_view.clear()
        self.debug_drawer.clear()

    def _on_config_saved(self, new_config: AgentConfig):
        self.config = new_config
        self.controller.reconfigure(new_config)
        self.chat_view.clear()
        self.debug_drawer.clear()
        self.debug_drawer.add_event(
            "System",
            f"Config updated: {new_config.provider} / {new_config.model}",
            "#6366F1",
        )

    def _manual_compact(self):
        self.page.run_task(self._do_compact)

    async def _do_compact(self):
        from compact.compact import compact_conversation
        from compact.grouping import estimate_tokens

        pre = estimate_tokens(self.controller.agent.messages)
        try:
            result = await compact_conversation(
                self.controller.agent.provider,
                self.controller.agent.messages,
                self.controller.agent.registry.get_schemas(),
                keep_recent_rounds=2,
                log_path=self._log_path,
            )
            if result.summary_messages:
                self.controller.agent.messages = (
                    result.summary_messages + result.messages_to_keep
                )
                self.controller.agent._last_actual_tokens = result.post_tokens
                self.controller.agent._compact_count += 1
                await self.handler.on_compact(
                    pre, result.post_tokens,
                    f"manual (#{self.controller.agent._compact_count})",
                )
            else:
                await self.handler.on_compact(pre, pre, "skipped (not enough messages)")
        except Exception as e:
            await self.handler.on_compact(pre, pre, f"failed: {e}")

    def _on_keyboard(self, e: ft.KeyboardEvent):
        if e.ctrl and e.key == "Enter":
            text = self.input_bar._text_field.value.strip()
            if text:
                self._on_send(text)
                self.input_bar._text_field.value = ""
                self.input_bar._text_field.update()


def launch_flet(config: AgentConfig):
    """Entry point for Flet desktop mode."""

    def main(page: ft.Page):
        FletApp(page, config)

    ft.app(target=main)
