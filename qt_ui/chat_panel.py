"""Chat panel: scrollable message bubbles."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QLabel, QSizePolicy,
)


def _make_bubble(text: str, align: str, max_width_ratio: float,
                 bg: str, color: str) -> QLabel:
    """Create a message bubble label with plain-text rendering."""
    label = QLabel(text)
    label.setTextFormat(Qt.PlainText)
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    fm = label.fontMetrics()
    label.setMaximumWidth(int(fm.averageCharWidth() * 1200 * max_width_ratio))
    label.setStyleSheet(f"""
        background: {bg};
        color: {color};
        padding: 8px 14px;
        border-radius: 12px;
        font-size: 14px;
    """)
    if align == "right":
        label.setAlignment(Qt.AlignRight)
    return label


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

    def set_title(self, text: str):
        self._title.setText(text)

    def add_user_message(self, text: str):
        label = _make_bubble(text, "right", 0.7, "#0e639c", "white")
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, label,
                                       alignment=Qt.AlignRight)

    def add_assistant_message(self, text: str):
        label = _make_bubble(text, "left", 0.8, "#3c3c3c", "#d4d4d4")
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
        if not self._thinking_label:
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
