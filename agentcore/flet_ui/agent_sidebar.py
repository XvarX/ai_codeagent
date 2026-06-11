"""Agent sidebar — shows agent list, allows switching."""

import flet as ft


AGENT_STATUS_COLORS = {
    "running": "#3B82F6",
    "completed": "#22C55E",
    "failed": "#EF4444",
    "killed": "#94A3B8",
    "pending": "#F59E0B",
}


class AgentSidebar(ft.Container):
    """Collapsible sidebar showing running and completed agents."""

    def __init__(self, manager, on_switch=None):
        super().__init__()
        self.manager = manager
        self.on_switch = on_switch
        self._expanded = False
        self._collapsed_width = 32
        self._expanded_width = 220
        self.width = self._collapsed_width
        self.bgcolor = "#F8FAFC"
        self.border = ft.Border(right=ft.BorderSide(1, "#E2E6EC"))
        self.padding = ft.Padding(8, 12, 8, 12)
        self.animate = ft.Animation(200, ft.AnimationCurve.EASE_OUT)
        self.visible = False

        self._toggle_btn = ft.IconButton(
            icon=ft.icons.Icons.KEYBOARD_ARROW_RIGHT,
            icon_size=16,
            on_click=self._toggle,
            style=ft.ButtonStyle(padding=ft.Padding(4, 4, 4, 4)),
        )

        self._agent_list = ft.Column(spacing=6, tight=True)

        self._expanded_content = ft.Column([
            ft.Row([
                ft.Text("Agents", size=16, weight=ft.FontWeight.W_600, color="#475569"),
                self._toggle_btn,
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(height=1, color="#E2E6EC"),
            self._agent_list,
        ], spacing=8, tight=True, visible=False)

        self._collapsed_content = ft.Column([
            self._toggle_btn,
        ], spacing=4, tight=True, alignment=ft.MainAxisAlignment.START)

        self.content = ft.Column([
            self._expanded_content,
            self._collapsed_content,
        ], spacing=0, tight=True)

    def _toggle(self, e):
        self._expanded = not self._expanded
        if self._expanded:
            self.width = self._expanded_width
            self._toggle_btn.icon = ft.icons.Icons.KEYBOARD_ARROW_LEFT
            self._expanded_content.visible = True
            self._collapsed_content.visible = False
        else:
            self.width = self._collapsed_width
            self._toggle_btn.icon = ft.icons.Icons.KEYBOARD_ARROW_RIGHT
            self._expanded_content.visible = False
            self._collapsed_content.visible = True
        self.update()

    def refresh(self):
        """Rebuild the agent list from current AgentManager state."""
        self._agent_list.controls.clear()

        main_state = self.manager.agents.get("1")
        self._agent_list.controls.append(self._build_entry(
            "1", "main",
            status="running" if main_state else "pending",
            is_active=(self.manager.active_id == "1"),
            subtitle="主 Agent",
        ))

        for state in self.manager.list_other_agents():
            label = state.name or state.definition.name
            subtitle = f"{state.est_tokens}t" if state.est_tokens else state.status
            self._agent_list.controls.append(self._build_entry(
                state.id, label, state.status,
                is_active=(self.manager.active_id == state.id),
                subtitle=subtitle,
            ))

        has_subagents = len(self.manager.list_other_agents()) > 0
        self.visible = has_subagents or self._expanded

        self.update()

    def _build_entry(self, agent_id: str, name: str, status: str,
                     is_active: bool = False, subtitle: str | None = None):
        dot_color = AGENT_STATUS_COLORS.get(status, "#94A3B8")
        bgcolor = "#E8ECF2" if is_active else None

        status_dot = ft.Container(
            width=8, height=8,
            border_radius=4,
            bgcolor=dot_color,
        )

        text_color = "#1E1B3A" if is_active else "#475569"
        texts = [ft.Text(name, size=16, color=text_color, weight=ft.FontWeight.W_500)]
        if subtitle:
            texts.append(ft.Text(subtitle, size=14, color="#94A3B8"))

        return ft.Container(
            content=ft.Row([
                status_dot,
                ft.Column(texts, spacing=1, tight=True),
            ], spacing=8),
            padding=ft.Padding(8, 6, 8, 6),
            border_radius=6,
            bgcolor=bgcolor,
            on_click=lambda e, aid=agent_id: self._switch_to(aid),
        )

    def _switch_to(self, agent_id: str):
        print(f"[Sidebar] switch to {agent_id}", flush=True)
        if self.on_switch:
            self.on_switch(agent_id)
        self.refresh()
