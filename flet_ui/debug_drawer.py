"""Collapsible debug drawer with context usage and event log."""

import flet as ft


class DebugDrawer(ft.Container):
    """Right-side debug panel with expand/collapse animation."""

    MIN_WIDTH = 200
    MAX_WIDTH = 600

    def __init__(self, on_compact=None, on_clear=None, on_event_click=None, on_toggle=None, max_tokens: int = 128000):
        super().__init__()
        self._on_compact = on_compact
        self._on_clear = on_clear
        self._on_event_click = on_event_click
        self._on_toggle_cb = on_toggle
        self._is_open = False
        self._expanded_width = 280
        self._max_tokens = max_tokens
        self._round_tag = 0  # current API-round tag for entries
        self._entry_id = 0   # auto-increment entry ID
        self._entry_rounds: list[tuple[object, int]] = []  # (control, round_tag)

        self.width = 36
        self.bgcolor = "#FAFBFC"
        self.border = ft.Border.only(left=ft.BorderSide(1, "#F1F3F6"))
        self.animate = ft.Animation(200, ft.AnimationCurve.EASE_OUT)
        self.padding = ft.Padding.all(0)

        # Collapsed view
        self._collapsed_view = ft.Container(
            content=ft.Column([
                ft.Container(height=12),
                ft.Text("调", size=10, color="#64748B", text_align=ft.TextAlign.CENTER),
                ft.Text("试", size=10, color="#64748B", text_align=ft.TextAlign.CENTER),
                ft.Container(
                    width=6, height=6, border_radius=3,
                    bgcolor="#E2E6EC",
                ),
            ], alignment=ft.MainAxisAlignment.START,
               horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(vertical=14),
            on_click=self._toggle,
        )

        # Expanded view — built lazily
        self._expanded_view = None
        self._event_log = ft.ListView(spacing=1, padding=ft.Padding.only(top=4),
                                      auto_scroll=True)

        self._usage_bar = ft.ProgressBar(value=0, color="#6366F1", bgcolor="#E8E8EF",
                                         bar_height=6)
        self._usage_text = ft.Text("-- tokens", size=10, color="#64748B")

        self.content = self._collapsed_view

    def _build_expanded(self):
        title_bar = ft.Row([
            ft.Text("调试面板", size=12, weight=ft.FontWeight.W_600, color="#1E1B3A"),
            ft.IconButton(icon=ft.Icons.CLOSE, icon_size=14, icon_color="#64748B",
                          on_click=self._toggle),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        compact_btn = ft.TextButton(
            content=ft.Text("Compact", size=10, color="#64748B"),
            style=ft.ButtonStyle(
                padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            ),
            on_click=lambda e: self._on_compact and self._on_compact(),
        )
        clear_btn = ft.TextButton(
            content=ft.Text("Clear History", size=10, color="#EF4444"),
            style=ft.ButtonStyle(
                padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            ),
            on_click=lambda e: self._on_clear and self._on_clear(),
        )

        return ft.Column([
            title_bar,
            ft.Divider(height=1, color="#EEF0F4"),
            ft.Container(height=6),
            ft.Text("上下文窗口", size=10, color="#64748B"),
            ft.Container(height=4),
            self._usage_bar,
            ft.Container(height=2),
            self._usage_text,
            ft.Container(height=10),
            ft.Text("事件日志", size=10, color="#64748B"),
            ft.Container(
                content=self._event_log,
                expand=True,
                bgcolor="#F8F9FB",
                border_radius=6,
                padding=ft.Padding.all(8),
                border=ft.Border.all(1, "#EEF0F4"),
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
            self.animate = ft.Animation(200, ft.AnimationCurve.EASE_OUT)
        else:
            self.width = self._expanded_width
            self._is_open = True
            if self._expanded_view is None:
                self._expanded_view = self._build_expanded()
            self.content = ft.Container(
                content=self._expanded_view,
                padding=ft.Padding.all(12),
            )
        if self._on_toggle_cb:
            self._on_toggle_cb(self._is_open)
        self.update()

    def add_event(self, prefix: str, message: str, color: str, event_data: dict = None) -> int:
        # Capture event_data in closure to avoid index mismatch
        captured_data = event_data
        eid = self._entry_id
        self._entry_id += 1
        round_tag = self._round_tag

        def on_click(e, data=captured_data):
            if data and self._on_event_click:
                self._on_event_click(data)

        is_first = len(self._event_log.controls) == 0
        if not is_first:
            self._event_log.controls.append(
                ft.Divider(height=1, color="#E8EAF0")
            )

        entry = ft.Container(
            content=ft.Column([
                ft.Text(prefix, size=10, weight=ft.FontWeight.W_600, color=color),
                ft.Text(message, size=9, color="#475569",
                        max_lines=3, overflow=ft.TextOverflow.ELLIPSIS),
            ], spacing=0, tight=True),
            padding=ft.Padding.only(left=4, right=4, top=1, bottom=1),
            border_radius=4,
            on_click=on_click if self._on_event_click else None,
        )
        self._event_log.controls.append(entry)
        self._entry_rounds.append((entry, round_tag))
        if len(self._event_log.controls) > 100:  # div+entry pairs
            self._event_log.controls = self._event_log.controls[-100:]
            self._entry_rounds = self._entry_rounds[-100:]
        if self._is_open and self._event_log.page:
            self._event_log.update()
        return eid

    def update_context_usage(self, usage: dict) -> None:
        prompt = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0) or 0
        completion = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0) or 0
        total = usage.get("total_tokens", 0) or prompt + completion
        ratio = min(total / max(self._max_tokens, 1), 1.0)
        self._usage_bar.value = ratio
        self._usage_text.value = f"~{total}  tokens  ({int(ratio * 100)}%)"
        if self._is_open and self._usage_bar.page:
            self._usage_bar.update()
            self._usage_text.update()

    def advance_round(self):
        """Increment round tag — call when a new API round starts."""
        self._round_tag += 1

    def mark_entries_gray(self, up_to_round: int):
        """Gray out all entries with round_tag <= up_to_round."""
        for ctrl, tag in self._entry_rounds:
            if tag <= up_to_round:
                ctrl.opacity = 0.4
        if self._is_open and self._event_log.page:
            self._event_log.update()

    def clear(self) -> None:
        self._entry_rounds.clear()
        self._event_log.controls.clear()
        if self._is_open and self._event_log.page:
            self._event_log.update()
