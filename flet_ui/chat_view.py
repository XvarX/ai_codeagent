"""Chat bubble list with Markdown rendering."""

import flet as ft


class ChatView(ft.ListView):
    """Scrollable chat message list."""

    def __init__(self):
        super().__init__()
        self.expand = True
        self.spacing = 10
        self.padding = ft.Padding.symmetric(horizontal=18, vertical=14)
        self.auto_scroll = True
        self._thinking_row: ft.Row | None = None

    def add_user_message(self, text: str) -> None:
        bubble = ft.Container(
            content=ft.Text(text, size=12, color="#1E1B3A", selectable=True),
            bgcolor="#F1F3F6",
            border=ft.Border.all(1, "#EAEAEF"),
            border_radius=ft.BorderRadius.only(
                top_left=15, top_right=15, bottom_left=15, bottom_right=3,
            ),
            padding=ft.Padding.symmetric(horizontal=15, vertical=10),
            alignment=ft.alignment.center_right,
        )
        row = ft.Row([bubble], alignment=ft.MainAxisAlignment.END)
        self.controls.append(row)

    def add_assistant_message(self, markdown_text: str) -> None:
        avatar = ft.Container(
            content=ft.Text("AI", size=10, color="white", weight=ft.FontWeight.W_600),
            width=28, height=28,
            border_radius=14,
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_left,
                end=ft.alignment.bottom_right,
                colors=["#6366F1", "#8B5CF6"],
            ),
            alignment=ft.alignment.center,
            shadow=ft.BoxShadow(
                blur_radius=4, color=ft.colors.with_opacity(0.25, "#6366F1"),
                offset=ft.Offset(0, 1),
            ),
        )
        bubble = ft.Container(
            content=ft.Markdown(
                markdown_text,
                selectable=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                code_theme="atom-one-light",
                code_style=ft.TextStyle(
                    size=11, font_family="monospace",
                ),
                auto_follow_links=True,
            ),
            bgcolor="#FAFBFC",
            border=ft.Border.all(1, "#EEF0F4"),
            border_radius=ft.BorderRadius.only(
                top_left=3, top_right=15, bottom_left=15, bottom_right=15,
            ),
            padding=ft.Padding.symmetric(horizontal=15, vertical=10),
        )
        row = ft.Row(
            [avatar, bubble],
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
        self.controls.append(row)

    def add_tool_label(self, name: str, preview: str) -> None:
        label = ft.Container(
            content=ft.Text(
                f"{name}  {preview}",
                size=10, color="#64748B",
            ),
            bgcolor="#F8F9FB",
            border=ft.Border.all(1, "#EEF0F4"),
            border_radius=6,
            padding=ft.Padding.symmetric(horizontal=9, vertical=3),
        )
        row = ft.Row([label], alignment=ft.MainAxisAlignment.START)
        self.controls.append(row)

    def show_thinking(self) -> None:
        if self._thinking_row is not None:
            return
        dots = ft.Row(
            [
                ft.Container(width=6, height=6, border_radius=3,
                             bgcolor="#A0A0B8"),
                ft.Container(width=6, height=6, border_radius=3,
                             bgcolor="#A0A0B8"),
                ft.Container(width=6, height=6, border_radius=3,
                             bgcolor="#A0A0B8"),
            ],
            spacing=4,
        )
        label = ft.Text("思考中...", size=10, color="#A0A0B8")
        self._thinking_row = ft.Row(
            [dots, label], spacing=6,
            alignment=ft.MainAxisAlignment.START,
        )
        self.controls.append(self._thinking_row)

    def hide_thinking(self) -> None:
        if self._thinking_row is not None:
            self.controls.remove(self._thinking_row)
            self._thinking_row = None

    def clear(self) -> None:
        self._thinking_row = None
        self.controls.clear()
