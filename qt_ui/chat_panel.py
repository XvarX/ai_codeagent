"""Chat panel: scrollable message bubbles with Markdown rendering."""

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextDocument, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QLabel, QTextEdit, QSizePolicy,
)


def _md_to_html(text: str) -> str:
    """Convert basic Markdown to HTML for QTextEdit rendering."""
    html = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Code blocks
    html = re.sub(r'```(\w*)\n(.*?)```',
                  r'<pre style="background:#1e1e1e;color:#ce9178;padding:8px;border-radius:6px;font-size:13px;margin:4px 0">\2</pre>',
                  html, flags=re.DOTALL)
    # Inline code
    html = re.sub(r'`([^`]+)`',
                  r'<code style="background:#333;color:#ce9178;padding:1px 4px;border-radius:3px;">\1</code>',
                  html)
    # Bold / Italic
    html = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html)
    html = re.sub(r'\*(.+?)\*', r'<i>\1</i>', html)
    # Headers
    html = re.sub(r'^### (.+)$', r'<h3 style="margin:4px 0">\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<h2 style="margin:4px 0">\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.+)$', r'<h1 style="margin:4px 0">\1</h1>', html, flags=re.MULTILINE)
    # Unordered lists
    html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    html = re.sub(r'(<li>.*</li>)', r'<ul style="margin:4px 0">\1</ul>', html, flags=re.DOTALL)

    # Line breaks: use <p> for paragraphs, single <br> for single newlines
    # Split on double-newline (paragraph break), then join with single newlines
    paragraphs = html.split("\n\n")
    result_parts = []
    for para in paragraphs:
        if para.strip():
            lines = para.split("\n")
            result_parts.append("<br>".join(lines))
    html = '<p style="margin:2px 0;line-height:1.4">' + '</p><p style="margin:2px 0;line-height:1.4">'.join(result_parts) + '</p>'

    return html


def _measure_text_rect(text: str, font: QFont, max_width: int) -> tuple[int, int]:
    """Measure text height at given width. Returns (width, height)."""
    doc = QTextDocument()
    doc.setDefaultFont(font)
    # Use plain text for measurement accuracy
    doc.setPlainText(text)
    doc.setTextWidth(max_width - 24)
    return int(doc.size().width()), int(doc.size().height())


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
        _, h = _measure_text_rect(text, self.font(), max_w)
        h = max(h + 40, 44)  # padding + safe margin

        label = QLabel(text)
        label.setTextFormat(Qt.PlainText)
        label.setWordWrap(True)
        label.setContentsMargins(14, 12, 14, 12)
        label.setFixedWidth(max_w)
        label.setMinimumHeight(h)
        label.setMaximumHeight(h + 40)  # allow some grow
        label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
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

        html = _md_to_html(text)

        bubble = QTextEdit()
        bubble.setReadOnly(True)
        bubble.setHtml(html)
        bubble.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        bubble.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        bubble.setFixedWidth(max_w)
        bubble.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        bubble.setStyleSheet("""
            QTextEdit {
                background: #3c3c3c;
                color: #d4d4d4;
                border: none;
                border-radius: 12px;
                font-size: 14px;
                padding: 10px 12px;
            }
        """)

        # Measure rendered HTML height
        doc = bubble.document()
        doc.setTextWidth(max_w - 24)
        rendered_h = int(doc.size().height() + 24)

        bubble.setMinimumHeight(max(rendered_h, 40))
        bubble.setMaximumHeight(max(rendered_h, 40))

        self._msg_layout.insertWidget(self._msg_layout.count() - 1, bubble,
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
