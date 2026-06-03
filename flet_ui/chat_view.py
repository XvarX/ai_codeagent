"""Chat bubble list with Markdown rendering."""

import re
import flet as ft


def flatten_headings(text: str) -> str:
    """Convert # headings to bold text, preserving fenced code blocks."""
    lines = text.split("\n")
    result = []
    in_fence = False
    for line in lines:
        if line.startswith("```"):
            in_fence = not in_fence
            result.append(line)
        elif not in_fence:
            m = re.match(r"^(#{1,6})\s+(.+)", line)
            if m:
                result.append(f"**{m.group(2)}**")
            else:
                result.append(line)
        else:
            result.append(line)
    return "\n".join(result)


class ChatView(ft.ListView):
    """Scrollable chat message list."""

    def __init__(self):
        super().__init__()
        self.expand = True
        self.spacing = 10
        self.padding = ft.Padding.symmetric(horizontal=18, vertical=14)
        self.auto_scroll = True
        self._thinking_row: ft.Row | None = None

    def _try_update(self):
        try:
            self.update()
        except RuntimeError:
            pass

    def add_user_message(self, text: str) -> None:
        bubble = ft.Container(
            content=ft.Text(text, size=17, color="#1E1B3A", selectable=True),
            bgcolor="#F1F3F6",
            border=ft.Border.all(1, "#EAEAEF"),
            border_radius=ft.BorderRadius.only(
                top_left=15, top_right=15, bottom_left=15, bottom_right=3,
            ),
            padding=ft.Padding.symmetric(horizontal=15, vertical=10),
            alignment=ft.alignment.Alignment.CENTER_RIGHT,
        )
        row = ft.Row([bubble], alignment=ft.MainAxisAlignment.END)
        self.controls.append(row)
        self._try_update()

    def add_assistant_message(self, markdown_text: str) -> None:
        avatar = ft.Container(
            content=ft.Text("AI", size=14, color="white", weight=ft.FontWeight.W_600),
            width=28, height=28,
            border_radius=14,
            gradient=ft.LinearGradient(
                begin=ft.alignment.Alignment.TOP_LEFT,
                end=ft.alignment.Alignment.BOTTOM_RIGHT,
                colors=["#6366F1", "#8B5CF6"],
            ),
            alignment=ft.alignment.Alignment.CENTER,
            shadow=ft.BoxShadow(
                blur_radius=4, color=ft.Colors.with_opacity(0.25, "#6366F1"),
                offset=ft.Offset(0, 1),
            ),
        )
        bubble = ft.Container(
            content=ft.Markdown(
                flatten_headings(markdown_text),
                selectable=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                code_theme="atom-one-light",
                auto_follow_links=True,
                md_style_sheet=ft.MarkdownStyleSheet(
                    p_text_style=ft.TextStyle(size=16),
                    h1_text_style=ft.TextStyle(size=24, weight=ft.FontWeight.W_700),
                    h2_text_style=ft.TextStyle(size=22, weight=ft.FontWeight.W_600),
                    h3_text_style=ft.TextStyle(size=20, weight=ft.FontWeight.W_600),
                    code_text_style=ft.TextStyle(size=15, font_family="Consolas"),
                    strong_text_style=ft.TextStyle(size=16, weight=ft.FontWeight.W_700),
                ),
            ),
            bgcolor="#EBEEF2",
            border=ft.Border.all(1, "#DDE0E5"),
            border_radius=ft.BorderRadius.only(
                top_left=3, top_right=15, bottom_left=15, bottom_right=15,
            ),
            padding=ft.Padding.symmetric(horizontal=15, vertical=10),
            expand=True,
        )
        row = ft.Row(
            [avatar, bubble],
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
        self.controls.append(row)
        self._try_update()

    def add_tool_label(self, name: str, preview: str) -> None:
        label = ft.Container(
            content=ft.Text(
                f"{name}  {preview}",
                size=14, color="#475569",
            ),
            bgcolor="#F8F9FB",
            border=ft.Border.all(1, "#EEF0F4"),
            border_radius=6,
            padding=ft.Padding.symmetric(horizontal=9, vertical=3),
        )
        row = ft.Row([label], alignment=ft.MainAxisAlignment.START)
        self.controls.append(row)
        self._try_update()

    def add_diff_viewer(self, viewer) -> None:
        self.controls.append(ft.Row([viewer], alignment=ft.MainAxisAlignment.START))
        self._try_update()

    def show_thinking(self) -> None:
        if self._thinking_row is not None:
            return
        dots = ft.Row(
            [
                ft.Container(width=6, height=6, border_radius=3,
                             bgcolor="#94A3B8"),
                ft.Container(width=6, height=6, border_radius=3,
                             bgcolor="#94A3B8"),
                ft.Container(width=6, height=6, border_radius=3,
                             bgcolor="#94A3B8"),
            ],
            spacing=4,
        )
        label = ft.Text("思考中...", size=14, color="#94A3B8")
        self._thinking_row = ft.Row(
            [dots, label], spacing=6,
            alignment=ft.MainAxisAlignment.START,
        )
        self.controls.append(self._thinking_row)
        self._try_update()

    def hide_thinking(self) -> None:
        if self._thinking_row is not None:
            self.controls.remove(self._thinking_row)
            self._thinking_row = None
            self.update()

    def clear(self) -> None:
        self._thinking_row = None
        self.controls.clear()
        self._try_update()
