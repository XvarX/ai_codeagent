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

    async def on_text_delta(self, token: str, reasoning: bool = False):
        self.app._on_text_delta(token, reasoning)

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
            on_event_click=self._on_debug_event_click,
        )
        self.input_bar = InputBar(on_send=self._on_send)

        self._current_assistant_bubble: ft.Container | None = None
        self._current_md_text: str = ""
        self._log_path = self._init_log()

        self._stored_events: list[dict] = []  # indexed same as debug_drawer._event_data

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
                        begin=ft.alignment.Alignment.TOP_LEFT,
                        end=ft.alignment.Alignment.BOTTOM_RIGHT,
                        colors=["#6366F1", "#8B5CF6"],
                    ),
                    alignment=ft.alignment.Alignment.CENTER,
                ),
                ft.Text("AI Code Agent", size=14, weight=ft.FontWeight.W_600,
                        color="#1E1B3A"),
                ft.Container(
                    content=ft.Text(
                        f"{self.config.provider}  |  {self.config.model or 'default'}",
                        size=10, color="#64748B",
                    ),
                    bgcolor="#F1F3F6", border_radius=4,
                    padding=ft.Padding.symmetric(horizontal=7, vertical=2),
                ),
            ], spacing=10),
            actions=[
                ft.TextButton(
                    content=ft.Text("配置", size=11, color="#64748B"),
                    on_click=lambda e: show_config_dialog(
                        self.page, on_save=self._on_config_saved),
                ),
                ft.TextButton(
                    content=ft.Text("清除", size=11, color="#64748B"),
                    on_click=lambda e: self._clear_history(),
                ),
                ft.TextButton(
                    content=ft.Text("调试", size=11, color="#64748B"),
                    on_click=lambda e: self.debug_drawer._toggle(),
                ),
            ],
            bgcolor="#FAFBFC",
        )

        main_row = ft.Row(
            [self.chat_view, self.debug_drawer],
            spacing=0,
            expand=True,
        )

        layout = ft.Column(
            [main_row, self.input_bar],
            spacing=0,
            expand=True,
        )
        self.page.add(layout)

        self.page.on_keyboard_event = self._on_keyboard

        # Startup system info
        registry = self.controller.registry
        self.debug_drawer.add_event(
            "System",
            f"Provider: {self.config.provider}  |  Model: {self.config.model or 'default'}\n"
            f"Tools: {', '.join(registry.get_tool_names())}\n"
            f"CWD: {self.config.cwd or Path.cwd()}",
            "#569cd6",
        )

    def _on_thinking(self):
        self.chat_view.show_thinking()

    def _on_text_delta(self, token: str, reasoning: bool = False):
        if reasoning:
            return  # skip internal thinking, don't show in chat
        self._current_md_text += token
        if self._current_assistant_bubble is None:
            avatar = ft.Container(
                content=ft.Text("AI", size=10, color="white",
                               weight=ft.FontWeight.W_600),
                width=28, height=28, border_radius=14,
                gradient=ft.LinearGradient(
                    begin=ft.alignment.Alignment.TOP_LEFT,
                    end=ft.alignment.Alignment.BOTTOM_RIGHT,
                    colors=["#6366F1", "#8B5CF6"],
                ),
                alignment=ft.alignment.Alignment.CENTER,
                shadow=ft.BoxShadow(
                    blur_radius=4,
                    color=ft.Colors.with_opacity(0.25, "#6366F1"),
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
            )
        self.page.update()

    def _on_tool_use(self, name: str, input_dict: dict):
        preview = ", ".join(
            f"{k}={str(v)[:40]!r}" for k, v in input_dict.items()
        )
        self.chat_view.add_tool_label(name, preview)
        detail = "\n".join(
            f"  {k}: {str(v)[:200]}" for k, v in input_dict.items()
        )
        self.debug_drawer.add_event(
            f"[Tool] {name}", detail, "#6366F1",
            event_data={"type": "Tool", "name": name, "input": input_dict,
                        "formatted": f"Tool: {name}\n\n" + detail,
                        "raw_json": json.dumps(input_dict, ensure_ascii=False, indent=2)},
        )

    def _on_tool_result(self, name: str, result: str, is_error: bool):
        color = "#EF4444" if is_error else "#10B981"
        preview = result[:500].replace("\n", " ")
        self.debug_drawer.add_event(
            f"[Tool] {name} done",
            f"  status: {'ERROR' if is_error else 'OK'}  |  size: {len(result)} chars\n"
            f"  {preview}",
            color,
            event_data={
                "type": "Tool Result",
                "name": name,
                "result": result,
                "is_error": is_error,
                "formatted": f"Tool: {name}\n"
                            f"Status: {'ERROR' if is_error else 'OK'}\n"
                            f"Size: {len(result)} chars\n\n{result[:5000]}",
                "raw_json": json.dumps(
                    {"tool": name, "result": result, "is_error": is_error},
                    ensure_ascii=False, indent=2),
            },
        )

    def _on_response_done(self, raw: dict):
        # Save text before clearing
        final_text = self._current_md_text
        if self._current_assistant_bubble is not None:
            self._current_assistant_bubble.content = ft.Markdown(
                final_text,
                selectable=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                code_theme="atom-one-light",
            )
            self.page.update()
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
        total_tokens = norm_usage.get("total_tokens", "?")
        cache_read = norm_usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)

        resp_lines = [f"Model: {model}  |  Msgs: {len(msgs)}"]
        resp_lines.append(f"prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens}")
        if cache_read:
            resp_lines.append(f"cache hit: {cache_read} tokens ({cache_read * 100 // max(prompt_tokens, 1)}%)")
        tool_blocks = raw.get("_tool_use_blocks", [])
        if tool_blocks:
            resp_lines.append("Tool calls: " + ", ".join(t["tool_name"] for t in tool_blocks))
        else:
            text_preview = final_text[:200].replace("\n", " ")
            resp_lines.append(f"Text: {text_preview}")
        # Store full response data for detail dialog
        response_data = {
            "type": "Response",
            "model": model,
            "raw": raw,
            "raw_json": json.dumps(raw, ensure_ascii=False, indent=2),
            "formatted": "\n".join(resp_lines),
            "text": final_text,
        }
        self.debug_drawer.add_event(
            "[Response]", "\n".join(resp_lines), "#10B981",
            event_data=response_data,
        )

    def _on_done(self, final_text: str):
        self.chat_view.hide_thinking()
        self.input_bar.set_busy(False)

    def _on_debug_event_click(self, event_data: dict):
        """Open detail dialog when a debug event entry is clicked."""
        if not event_data:
            return
        self._show_detail_dialog(event_data)

    def _show_detail_dialog(self, data: dict):
        event_type = data.get("type", "")
        formatted = data.get("formatted", "")
        raw_json = data.get("raw_json", "")

        if event_type == "Request":
            lines = [f"Model: {data.get('model', '?')}"]
            lines.append(f"Messages: {data.get('message_count', '?')}  |  "
                        f"~{data.get('est_tokens', '?')} tokens  |  "
                        f"{data.get('tools_count', '?')} tools")
            lines.append(f"=== User Message ===")
            lines.append(data.get('user_message', ''))
            lines.append("=== History ===")
            for i, m in enumerate(data.get("messages", [])):
                role = m["role"]
                content = m["content"]
                tool_blocks = m.get("tool_use_blocks", [])
                if tool_blocks:
                    for tb in tool_blocks:
                        lines.append(f"[{i}] {role} -> tool_use: {tb['tool_name']}")
                        for k, v in tb.get("input", {}).items():
                            lines.append(f"     {k}: {str(v)[:200]}")
                else:
                    lines.append(f"[{i}] {role}: {content}")
            formatted = "\n".join(lines)
            raw_json = json.dumps({
                "model": data.get("model"),
                "messages": [
                    {"role": m["role"], "content": m["content"],
                     "tool_use_id": m.get("tool_use_id") or None,
                     "tool_use_blocks": m.get("tool_use_blocks") or None}
                    for m in data.get("messages", [])
                ],
            }, ensure_ascii=False, indent=2)

        formatted_text = ft.Text(
            formatted, size=11, color="#1E1B3A",
            font_family="monospace", selectable=True,
        )
        raw_text = ft.Text(
            raw_json, size=11, color="#1E1B3A",
            font_family="monospace", selectable=True,
        )

        content_area = ft.Column([formatted_text], expand=True, scroll=ft.ScrollMode.AUTO)

        self._dlg_tab = 0  # 0=formatted, 1=raw

        def make_tab_btn(label, idx):
            def click(e):
                self._dlg_tab = idx
                content_area.controls[0] = formatted_text if idx == 0 else raw_text
                for i, btn in enumerate(tab_row.controls):
                    btn.content.color = "#6366F1" if i == idx else "#64748B"
                    btn.update()
                content_area.update()
            return ft.TextButton(
                content=ft.Text(label, size=11, color="#6366F1" if idx == 0 else "#64748B"),
                on_click=click,
            )

        tab_row = ft.Row([
            make_tab_btn("格式化", 0),
            make_tab_btn("原始 JSON", 1),
        ], spacing=0)

        dlg = ft.AlertDialog(
            title=ft.Text(f"{event_type} 详情", size=14, weight=ft.FontWeight.W_600),
            content=ft.Column([
                tab_row,
                ft.Container(height=8),
                content_area,
            ], height=500, width=650),
            actions=[
                ft.TextButton(
                    content=ft.Text("关闭", color="#64748B"),
                    on_click=lambda e: self.page.pop_dialog(),
                ),
            ],
            shape=ft.RoundedRectangleBorder(radius=10),
        )
        self.page.show_dialog(dlg)

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

        # Show request info immediately
        provider_name = self.controller.agent.provider.model or self.config.provider
        agent = self.controller.agent
        msg_count = len(agent.messages) + 1
        est_tokens = agent.est_tokens() + len(text) // 2
        tools_count = len(agent.registry.get_schemas())

        # Build message summary (include current user message)
        msg_lines = [f"Model: {provider_name}"]
        msg_lines.append(f"Messages: {msg_count}  |  ~{est_tokens} tokens  |  {tools_count} tools")
        msg_lines.append(f"  [new] user: {text[:80]}")
        for i, m in enumerate(agent.messages[-5:]):
            role = m.role
            content_preview = (m.content or "")[:50].replace("\n", " ")
            if m.tool_use_id:
                msg_lines.append(f"  [{i}] tool({m.tool_use_id[:12]}): {content_preview}")
            else:
                msg_lines.append(f"  [{i}] {role}: {content_preview}")
        if len(agent.messages) > 5:
            msg_lines.append(f"  ... +{len(agent.messages) - 5} earlier messages")
        # Store full request data for detail dialog
        request_data = {
            "type": "Request",
            "provider": provider_name,
            "model": provider_name,
            "message_count": msg_count,
            "est_tokens": est_tokens,
            "tools_count": tools_count,
            "user_message": text,
            "messages": [
                {"role": m.role, "content": m.content or "",
                 "tool_use_id": getattr(m, "tool_use_id", ""),
                 "tool_use_blocks": [
                    {"tool_name": b.tool_name, "input": b.input}
                    for b in (getattr(m, "tool_use_blocks", None) or [])
                 ]}
                for m in agent.messages
            ],
            "formatted": "\n".join(msg_lines),
        }
        self.debug_drawer.add_event(
            "[Request]", "\n".join(msg_lines), "#569cd6",
            event_data=request_data,
        )
        self.page.update()

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
