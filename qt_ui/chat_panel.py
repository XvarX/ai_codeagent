"""Chat panel: scrollable message bubbles with streaming text support."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QLabel,
)


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

        self._streaming_bubble: QLabel | None = None

    def set_title(self, text: str):
        self._title.setText(text)

    def add_user_message(self, text: str):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setMaximumWidth(int(self.width() * 0.7))
        label.setStyleSheet("""
            background: #0e639c;
            color: white;
            padding: 8px 14px;
            border-radius: 12px;
            font-size: 14px;
        """)
        label.setAlignment(Qt.AlignRight)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, label,
                                       alignment=Qt.AlignRight)

    def add_assistant_message(self, text: str):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setMaximumWidth(int(self.width() * 0.8))
        label.setStyleSheet("""
            background: #3c3c3c;
            color: #d4d4d4;
            padding: 8px 14px;
            border-radius: 12px;
            font-size: 14px;
        """)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, label,
                                       alignment=Qt.AlignLeft)

    def add_tool_label(self, tool_name: str, input_preview: str):
        label = QLabel(f"🔧 {tool_name} — {input_preview}")
        label.setStyleSheet("""
            color: #c586c0;
            font-size: 12px;
            padding: 2px 8px;
        """)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, label,
                                       alignment=Qt.AlignLeft)

    def start_streaming(self):
        self._streaming_bubble = QLabel("  thinking...")
        self._streaming_bubble.setWordWrap(True)
        self._streaming_bubble.setMaximumWidth(int(self.width() * 0.8))
        self._streaming_bubble.setStyleSheet("""
            background: #3c3c3c;
            color: #888;
            font-style: italic;
            padding: 8px 14px;
            border-radius: 12px;
            font-size: 14px;
        """)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1,
                                       self._streaming_bubble,
                                       alignment=Qt.AlignLeft)
        self._streaming_first_token = True

    def append_token(self, token: str):
        if self._streaming_bubble:
            if getattr(self, '_streaming_first_token', False):
                self._streaming_first_token = False
                self._streaming_bubble.setText(token)
                self._streaming_bubble.setStyleSheet("""
                    background: #3c3c3c;
                    color: #d4d4d4;
                    padding: 8px 14px;
                    border-radius: 12px;
                    font-size: 14px;
                """)
            else:
                current = self._streaming_bubble.text()
                self._streaming_bubble.setText(current + token)
            self._scroll.verticalScrollBar().setValue(
                self._scroll.verticalScrollBar().maximum()
            )

    def finish_streaming(self):
        self._streaming_bubble = None

    def clear(self):
        while self._msg_layout.count() > 1:
            item = self._msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
