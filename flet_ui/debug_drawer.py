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
        self._entry_id = 0   # auto-increment entry ID
        self._entry_records: list[dict] = []  # {control, group_key, group_idx}

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

    def add_event(self, prefix: str, message: str, color: str, event_data: dict = None,
                  group_key: str = None) -> int:
        captured_data = event_data
        eid = self._entry_id
        self._entry_id += 1

        def on_click(e, data=captured_data):
            if data and self._on_event_click:
                self._on_event_click(data)

        is_first = len(self._event_log.controls) == 0
        if not is_first:
            self._event_log.controls.append(
                ft.Divider(height=1, color="#E8EAF0")
            )

        prefix_text = ft.Text(prefix, size=10, weight=ft.FontWeight.W_600, color=color)
        entry = ft.Container(
            content=ft.Column([
                prefix_text,
                ft.Text(message, size=9, color="#475569",
                        max_lines=3, overflow=ft.TextOverflow.ELLIPSIS),
            ], spacing=0, tight=True),
            padding=ft.Padding.only(left=4, right=4, top=1, bottom=1),
            border_radius=4,
            on_click=on_click if self._on_event_click else None,
        )
        self._event_log.controls.append(entry)
        self._entry_records.append({
            "control": entry, "group_key": group_key, "group_idx": None,
            "prefix": prefix, "prefix_text": prefix_text,
        })
        if len(self._event_log.controls) > 100:
            self._event_log.controls = self._event_log.controls[-100:]
            self._entry_records = self._entry_records[-100:]
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

    def sync_groups(self, messages: list):
        """Walk messages via group_by_api_round, backfill group_idx on entries.

        Group IDs are persistent: surviving entries keep their original
        number after snip; new groups get the next available ID.
        """
        from compact.grouping import group_by_api_round

        groups = group_by_api_round(messages)

        # Build lookup: message identity → renumbered group index
        asst_id_to_gi: dict[str, int] = {}
        tool_id_to_gi: dict[str, int] = {}
        user_msg_groups: list[int] = []

        for gi, group in enumerate(groups):
            for msg in group:
                if msg.role == "assistant" and msg.id:
                    asst_id_to_gi[msg.id] = gi
                elif msg.role == "user" and msg.tool_use_id:
                    tool_id_to_gi[msg.tool_use_id] = gi
                elif msg.role == "user" and not msg.is_tool_result and not msg.tool_use_id:
                    user_msg_groups.append(gi)

        # Build persistent group ID map: renumbered gi → persistent gid
        persistent: dict[int, int] = {}
        for rec in self._entry_records:
            gid = rec.get("group_idx")
            if gid is None or gid < 0 or rec["control"].opacity < 1.0:
                continue
            key = rec.get("group_key") or ""
            gi = None
            if key.startswith("asst:"):
                gi = asst_id_to_gi.get(key[5:])
            elif key.startswith("tool:"):
                gi = tool_id_to_gi.get(key[5:])
            if gi is not None:
                persistent[gi] = gid

        max_persistent = max(
            (rec["group_idx"] for rec in self._entry_records
             if rec["group_idx"] is not None and rec["group_idx"] >= 0
             and rec["control"].opacity >= 1.0),
            default=-1)
        next_gid = max_persistent + 1

        # Count already-assigned (non-grayed) "user" entries to skip
        user_idx = sum(1 for rec in self._entry_records
                      if rec.get("group_key") == "user"
                      and rec["group_idx"] is not None
                      and rec["control"].opacity >= 1.0)

        updated = False
        for rec in self._entry_records:
            key = rec.get("group_key") or ""
            if not key or rec["group_idx"] is not None:
                continue

            gi = None
            if key == "user":
                if user_idx < len(user_msg_groups):
                    gi = user_msg_groups[user_idx]
                    user_idx += 1
            elif key.startswith("asst:"):
                gi = asst_id_to_gi.get(key[5:])
            elif key.startswith("tool:"):
                gi = tool_id_to_gi.get(key[5:])

            if gi is not None:
                gid = persistent.get(gi, next_gid)
                rec["group_idx"] = gid
                if gid == next_gid:
                    persistent[gi] = gid
                    next_gid += 1
                pfx = rec.get("prefix", "")
                rec["prefix_text"].value = f"{pfx} · G{gid}"
                try:
                    rec["prefix_text"].update()
                except RuntimeError:
                    pass
                updated = True

        if updated and self._is_open:
            try:
                if self._event_log.page:
                    self._event_log.update()
            except RuntimeError:
                pass

    def mark_groups_gray(self, max_group: int):
        """Gray out entries with group_idx <= max_group (inclusive)."""
        for rec in self._entry_records:
            gi = rec.get("group_idx")
            if gi is not None and gi <= max_group:
                rec["control"].opacity = 0.4
                cur = rec["prefix_text"].value or ""
                if not cur.startswith("[Remove]"):
                    rec["prefix_text"].value = f"[Remove] {cur}"
                try:
                    if rec["control"].page:
                        rec["control"].update()
                        rec["prefix_text"].update()
                except RuntimeError:
                    pass
        try:
            if self._is_open and self._event_log.page:
                self._event_log.update()
        except RuntimeError:
            pass

    def clear(self) -> None:
        self._entry_records.clear()
        self._event_log.controls.clear()
        if self._is_open and self._event_log.page:
            self._event_log.update()
