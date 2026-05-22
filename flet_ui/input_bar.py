"""Bottom input bar with text field and send button."""

import flet as ft


class InputBar(ft.Container):
    """Multi-line input with send button."""

    def __init__(self, on_send=None):
        super().__init__()
        self._on_send_callback = on_send

        self._text_field = ft.TextField(
            hint_text="输入消息... (Ctrl+Enter 发送)",
            hint_style=ft.TextStyle(size=12, color="#64748B"),
            text_style=ft.TextStyle(size=12, color="#1E1B3A"),
            multiline=True,
            shift_enter=True,
            min_lines=1,
            max_lines=6,
            border=ft.InputBorder.NONE,
            expand=True,
            bgcolor="transparent",
            content_padding=ft.Padding.symmetric(horizontal=4, vertical=4),
        )

        self._send_button = ft.IconButton(
            icon=ft.Icons.SEND,
            icon_size=16,
            bgcolor="#6366F1",
            icon_color="white",
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=9),
                padding=ft.Padding.all(8),
            ),
        )

        self.content = ft.Row(
            [
                ft.Container(
                    content=self._text_field,
                    border=ft.Border.all(1, "#E2E6EC"),
                    border_radius=10,
                    padding=ft.Padding.symmetric(horizontal=14, vertical=9),
                    expand=True,
                    bgcolor="#FFFFFF",
                ),
                self._send_button,
            ],
            spacing=8,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.END,
        )

        self.bgcolor = "#FAFBFC"
        self.border = ft.Border.only(top=ft.BorderSide(1, "#F1F3F6"))
        self.padding = ft.Padding.symmetric(horizontal=18, vertical=10)

        self._send_button.on_click = self._on_send_click

    def _on_send_click(self, e):
        text = self._text_field.value.strip()
        if text and self._on_send_callback:
            self._on_send_callback(text)
            self._text_field.value = ""
            self._text_field.update()

    @property
    def on_send(self):
        return self._on_send_callback

    @on_send.setter
    def on_send(self, callback):
        self._on_send_callback = callback

    def set_busy(self, busy: bool) -> None:
        self._send_button.disabled = busy
        self._send_button.bgcolor = "#A5B4FC" if busy else "#6366F1"
        if self._send_button.page:
            self._send_button.update()
