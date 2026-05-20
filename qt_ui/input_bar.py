"""Bottom input bar: multi-line text input + send + stop buttons."""

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QTextEdit, QPushButton


class InputBar(QWidget):
    """Multi-line input area with send and stop buttons."""

    send_clicked = Signal(str)
    stop_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self._input = QTextEdit()
        self._input.setPlaceholderText("输入消息... (Ctrl+Enter 发送, Enter 换行)")
        self._input.setMaximumHeight(120)
        self._input.setMinimumHeight(40)
        self._input.setStyleSheet("""
            QTextEdit {
                background: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
            }
            QTextEdit:focus {
                border-color: #007acc;
            }
        """)

        self._send_btn = QPushButton("发送")
        self._send_btn.setFixedSize(70, 40)
        self._send_btn.setStyleSheet("""
            QPushButton {
                background: #0e639c;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover { background: #1177bb; }
            QPushButton:pressed { background: #0b5080; }
            QPushButton:disabled { background: #555; color: #999; }
        """)

        self._stop_btn = QPushButton("停止")
        self._stop_btn.setFixedSize(70, 40)
        self._stop_btn.setStyleSheet("""
            QPushButton {
                background: #8b0000;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover { background: #a00000; }
            QPushButton:pressed { background: #700000; }
            QPushButton:disabled { background: #555; color: #999; }
        """)
        self._stop_btn.setVisible(False)

        layout.addWidget(self._input)
        layout.addWidget(self._send_btn)
        layout.addWidget(self._stop_btn)

        self._send_btn.clicked.connect(self._on_send)
        self._stop_btn.clicked.connect(self._on_stop)

    def _on_send(self):
        text = self._input.toPlainText().strip()
        if text:
            self.send_clicked.emit(text)
            self._input.clear()

    def _on_stop(self):
        self.stop_clicked.emit()

    def set_streaming(self, streaming: bool):
        self._send_btn.setVisible(not streaming)
        self._stop_btn.setVisible(streaming)
        self._input.setEnabled(not streaming)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return and event.modifiers() & Qt.ControlModifier:
            self._on_send()
        else:
            super().keyPressEvent(event)
