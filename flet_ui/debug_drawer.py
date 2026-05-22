"""Collapsible debug drawer with context usage and event log."""

import flet as ft


class DebugDrawer(ft.Container):
    """Right-side debug panel with expand/collapse animation."""

    def __init__(self, on_compact=None, on_clear=None):
        super().__init__()
        self._on_compact = on_compact
        self._on_clear = on_clear
        self._is_open = False

        self.width = 36
        self.bgcolor = "#FAFBFC"
        self.border = ft.border.only(left=ft.BorderSide(1, "#F1F3F6"))
        self.animate = ft.Animation(200, ft.AnimationCurve.EASE_OUT)
        self.padding = ft.padding.all(0)

        # Collapsed view
        self._collapsed_view = ft.Container(
            content=ft.Column([
                ft.Container(height=12),
                ft.Text("调", size=10, color="#94A3B8", text_align=ft.TextAlign.CENTER),
                ft.Text("试", size=10, color="#94A3B8", text_align=ft.TextAlign.CENTER),
                ft.Container(
                    width=6, height=6, border_radius=3,
                    bgcolor="#E2E6EC",
                ),
            ], alignment=ft.MainAxisAlignment.START,
               horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.symmetric(vertical=14),
            on_click=self._toggle,
        )

        # Expanded view — built lazily
        self._expanded_view = None
        self._event_log = ft.ListView(spacing=2, padding=ft.padding.only(top=4),
                                      auto_scroll=True)

        self._usage_bar = ft.ProgressBar(value=0, color="#6366F1", bgcolor="#E8E8EF",
                                         bar_height=6)
        self._usage_text = ft.Text("-- tokens", size=10, color="#94A3B8")

        self.content = self._collapsed_view

    def _build_expanded(self):
        title_bar = ft.Row([
            ft.Text("调试面板", size=12, weight=ft.FontWeight.W_600, color="#1E1B3A"),
            ft.IconButton(icon=ft.icons.CLOSE, icon_size=14, icon_color="#94A3B8",
                          on_click=self._toggle),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        compact_btn = ft.TextButton(
            text="Compact", style=ft.ButtonStyle(
                color="#64748B", text_style=ft.TextStyle(size=10),
                padding=ft.padding.symmetric(horizontal=10, vertical=4),
            ),
            on_click=lambda e: self._on_compact and self._on_compact(),
        )
        clear_btn = ft.TextButton(
            text="Clear History", style=ft.ButtonStyle(
                color="#EF4444", text_style=ft.TextStyle(size=10),
                padding=ft.padding.symmetric(horizontal=10, vertical=4),
            ),
            on_click=lambda e: self._on_clear and self._on_clear(),
        )

        return ft.Column([
            title_bar,
            ft.Divider(height=1, color="#EEF0F4"),
            ft.Container(height=6),
            ft.Text("上下文窗口", size=10, color="#94A3B8"),
            ft.Container(height=4),
            self._usage_bar,
            ft.Container(height=2),
            self._usage_text,
            ft.Container(height=10),
            ft.Text("事件日志", size=10, color="#94A3B8"),
            ft.Container(
                content=self._event_log,
                expand=True,
                bgcolor="#F8F9FB",
                border_radius=6,
                padding=ft.padding.all(8),
                border=ft.border.all(1, "#EEF0F4"),
            ),
            ft.Container(height=8),
            ft.Row([compact_btn, clear_btn],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ], spacing=0)

    def _toggle(self, e=None):
        if self._is_open:
            self.width = 36
            self._is_open = False
            self.content = self._collapsed_view
        else:
            self.width = 280
            self._is_open = True
            if self._expanded_view is None:
                self._expanded_view = self._build_expanded()
            self.content = ft.Container(
                content=self._expanded_view,
                padding=ft.padding.all(12),
            )
        self.update()

    def add_event(self, prefix: str, message: str, color: str) -> None:
        entry = ft.Column([
            ft.Row([
                ft.Text(prefix, size=10, weight=ft.FontWeight.W_600, color=color),
            ]),
            ft.Text(message, size=9, color="#64748B", selectable=True,
                    max_lines=3, overflow=ft.TextOverflow.ELLIPSIS),
        ], spacing=1)
        self._event_log.controls.insert(0, entry)
        if len(self._event_log.controls) > 50:
            self._event_log.controls = self._event_log.controls[:50]
        if self._is_open and self._event_log.page:
            self._event_log.update()

    def update_context_usage(self, usage: dict) -> None:
        prompt = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0) or 0
        completion = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0) or 0
        total = usage.get("total_tokens", 0) or prompt + completion
        ratio = min(total / 100000, 1.0)
        self._usage_bar.value = ratio
        self._usage_text.value = f"~{total}  tokens  ({int(ratio * 100)}%)"
        if self._is_open and self._usage_bar.page:
            self._usage_bar.update()
            self._usage_text.update()

    def clear(self) -> None:
        self._event_log.controls.clear()
        if self._is_open and self._event_log.page:
            self._event_log.update()
