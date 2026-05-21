"""Chat panel: scrollable message bubbles with Markdown rendering."""

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QLabel, QSizePolicy,
)


def _md_to_rich_text(text: str) -> str:
    """Convert basic Markdown to simple HTML for QLabel RichText."""
    html = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Code blocks → styled <pre>
    html = re.sub(
        r'```(\w*)\n(.*?)```',
        r'<pre style="background:#1e1e1e;color:#ce9178;padding:6px">\2</pre>',
        html, flags=re.DOTALL,
    )
    # Inline code
    html = re.sub(
        r'`([^`]+)`',
        r'<code style="background:#333;color:#ce9178">\1</code>',
        html,
    )
    # Bold / Italic
    html = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html)
    html = re.sub(r'\*(.+?)\*', r'<i>\1</i>', html)
    # Headers
    html = re.sub(r'^### (.+)$', r'<b>\1</b>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<b>\1</b>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.+)$', r'<b>\1</b>', html, flags=re.MULTILINE)
    # List items
    html = re.sub(r'^- (.+)$', r'  \1', html, flags=re.MULTILINE)
    # Single newlines → <br>
    html = html.replace("\n", "<br>")

    return html


def _plain_to_rich(text: str) -> str:
    """Convert plain text to safe HTML (escape + <br> for newlines)."""
    html = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return html.replace("\n", "<br>")


def _measure_h(text: str, font, max_w: int) -> int:
    """Measure plain-text height at given width."""
    doc = QTextDocument()
    doc.setDefaultFont(font)
    doc.setPlainText(text)
    doc.setTextWidth(max_w - 24)
    return max(int(doc.size().height()) + 32, 40)


class ChatPanel(QWidget):
    """Scrollable chat area with message bubbles."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._title = QLabel("AI Code Agent")
        self._title.setStyleSheet("""
            background: #2d2d2d;
            color: #ccc;
            padding: 8px 16px;
            font-weight: bold;
            font-size: 14px;
            border-bottom: 1px solid #444;
        """)
        layout.addWidget(self._title)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: #1e1e1e; }")

        self._msg_container = QWidget()
        self._msg_layout = QVBoxLayout(self._msg_container)
        self._msg_layout.setAlignment(Qt.AlignTop)
        self._msg_layout.setContentsMargins(12, 12, 12, 12)
        self._msg_layout.setSpacing(10)
        self._msg_layout.addStretch()

        self._scroll.setWidget(self._msg_container)
        layout.addWidget(self._scroll)

        self._thinking_label: QLabel | None = None

    def _view_width(self) -> int:
        w = self._scroll.viewport().width()
        if w < 200:
            w = self.width()
        if w < 200:
            w = 800
        return w - 24

    def set_title(self, text: str):
        self._title.setText(text)

    def add_user_message(self, text: str):
        max_w = int(self._view_width() * 0.7)
        h = _measure_h(text, self.font(), max_w)
        display = _plain_to_rich(text)

        label = QLabel(display)
        label.setTextFormat(Qt.RichText)
        label.setWordWrap(True)
        label.setContentsMargins(14, 12, 14, 12)
        label.setFixedWidth(max_w)
        label.setMinimumHeight(h)
        label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
        label.setStyleSheet("""
            background: #0e639c;
            color: white;
            border-radius: 12px;
            font-size: 14px;
        """)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, label,
                                       alignment=Qt.AlignRight)

    def add_assistant_message(self, text: str):
        max_w = int(self._view_width() * 0.8)
        h = _measure_h(text, self.font(), max_w)
        display = _md_to_rich_text(text)

        label = QLabel(display)
        label.setTextFormat(Qt.RichText)
        label.setWordWrap(True)
        label.setContentsMargins(14, 12, 14, 12)
        label.setFixedWidth(max_w)
        label.setMinimumHeight(h)
        label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
        label.setStyleSheet("""
            background: #3c3c3c;
            color: #d4d4d4;
            border-radius: 12px;
            font-size: 14px;
        """)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, label,
                                       alignment=Qt.AlignLeft)

    def add_tool_label(self, tool_name: str, input_preview: str):
        label = QLabel(f"🔧 {tool_name} — {input_preview}")
        label.setTextFormat(Qt.PlainText)
        label.setStyleSheet("""
            color: #c586c0;
            font-size: 12px;
            padding: 2px 8px;
        """)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, label,
                                       alignment=Qt.AlignLeft)

    def show_thinking(self):
        self.hide_thinking()
        self._thinking_label = QLabel("  thinking...")
        self._thinking_label.setTextFormat(Qt.PlainText)
        self._thinking_label.setStyleSheet("""
            color: #888;
            font-style: italic;
            padding: 4px 8px;
            font-size: 13px;
        """)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1,
                                       self._thinking_label,
                                       alignment=Qt.AlignLeft)

    def hide_thinking(self):
        if self._thinking_label:
            self._thinking_label.deleteLater()
            self._thinking_label = None

    def clear(self):
        self._thinking_label = None
        while self._msg_layout.count() > 1:
            item = self._msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
