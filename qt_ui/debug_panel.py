"""Collapsible debug panel with context usage sub-panel."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QTextBrowser, QLabel,
    QProgressBar,
)


class ContextUsageWidget(QWidget):
    """Shows token usage breakdown with progress bars."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(4)

        self._header = QLabel("📊 上下文窗口占用  总计 — / —")
        self._header.setStyleSheet("""
            color: #007acc;
            font-weight: bold;
            font-size: 12px;
            padding: 4px 0;
        """)
        layout.addWidget(self._header)

        self._categories = {}
        for name, color in [
            ("System Prompt", "#569cd6"),
            ("对话消息", "#4ec9b0"),
            ("工具定义", "#c586c0"),
            ("缓存命中", "#ce9178"),
        ]:
            cat_widget = self._create_category(name, color)
            layout.addWidget(cat_widget)
            self._categories[name] = cat_widget

        self._total_bar = QProgressBar()
        self._total_bar.setMaximum(1000)
        self._total_bar.setValue(0)
        self._total_bar.setFormat("总计 — / —")
        self._total_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #444;
                border-radius: 4px;
                background: #252525;
                height: 18px;
                text-align: center;
                color: white;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background: #4ec9b0;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self._total_bar)

        self.setVisible(False)

    def _create_category(self, name: str, color: str):
        row = QWidget()
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(2)

        label = QLabel(name)
        label.setStyleSheet(f"color: {color}; font-size: 11px;")
        row_layout.addWidget(label)

        bar = QProgressBar()
        bar.setMaximum(1000)
        bar.setValue(0)
        bar.setFormat("")
        bar.setFixedHeight(8)
        bar.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                border-radius: 4px;
                background: #333;
            }}
            QProgressBar::chunk {{
                background: {color};
                border-radius: 3px;
            }}
        """)
        row_layout.addWidget(bar)

        row._label = label
        row._bar = bar
        return row

    def update_usage(self, usage: dict, model_max: int = 128000):
        prompt_tokens = usage.get("prompt_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)

        sys_tokens = 680
        prompt_details = usage.get("prompt_tokens_details", {}) or {}
        cached_tokens = prompt_details.get("cached_tokens", 0) or 0

        msg_tokens = prompt_tokens - sys_tokens - 48
        tools_tokens = 48

        self._update_row("System Prompt", sys_tokens, model_max)
        self._update_row("对话消息", max(msg_tokens, 0), model_max)
        self._update_row("工具定义", tools_tokens, model_max)
        self._update_row("缓存命中", cached_tokens, model_max)

        self._total_bar.setMaximum(model_max)
        self._total_bar.setValue(total_tokens)
        self._total_bar.setFormat(f"总计 {total_tokens:,} / {model_max:,}")

        pct = total_tokens / model_max * 100 if model_max else 0
        self._header.setText(
            f"📊 上下文窗口占用  总计 {total_tokens:,} / {model_max:,} ({pct:.1f}%)"
        )
        self.setVisible(True)

    def _update_row(self, name: str, tokens: int, max_tokens: int):
        row = self._categories.get(name)
        if not row:
            return
        row._label.setText(f"{name}  ({tokens:,})")
        row._bar.setMaximum(max_tokens)
        row._bar.setValue(tokens)


class DebugPanel(QDockWidget):
    """Dockable debug panel with log browser + context usage widget."""

    def __init__(self, parent=None):
        super().__init__("Debug Log", parent)
        self.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)
        self.setMinimumWidth(300)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._log = QTextBrowser()
        self._log.setStyleSheet("""
            QTextBrowser {
                background: #1a1a1a;
                color: #888;
                font-size: 12px;
                border: none;
                padding: 8px;
            }
        """)
        layout.addWidget(self._log, stretch=1)

        self._context = ContextUsageWidget()
        layout.addWidget(self._context)

        self.setWidget(container)

    def add_entry(self, title: str, content: str, color: str = "#888"):
        self._log.append(
            f'<p><b style="color:{color}">{title}</b></p>'
            f'<pre style="font-size:11px;color:#999;margin:4px 0">{content}</pre>'
            f'<hr style="border-color:#333">'
        )

    def update_context_usage(self, usage: dict, model_max: int = 128000):
        self._context.update_usage(usage, model_max)

    def clear(self):
        self._log.clear()
