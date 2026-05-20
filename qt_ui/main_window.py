"""Main Qt window: assembles ChatPanel, DebugPanel, InputBar, AgentWorker."""

import json
import sys
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QStatusBar, QApplication,
)

from config import AgentConfig
from tools.registry import ToolRegistry
from tools.bash import BashTool
from tools.file_read import FileReadTool
from tools.file_edit import FileEditTool
from tools.file_write import FileWriteTool
from tools.glob import GlobTool
from tools.grep import GrepTool
from providers.anthropic import AnthropicProvider
from providers.openai_compat import OpenAICompatProvider
from agent import Agent
from qt_ui.chat_panel import ChatPanel
from qt_ui.debug_panel import DebugPanel
from qt_ui.input_bar import InputBar
from qt_ui.agent_worker import AgentWorker


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register_all([
        BashTool(), FileReadTool(), FileEditTool(),
        FileWriteTool(), GlobTool(), GrepTool(),
    ])
    return registry


def build_provider(config: AgentConfig):
    provider_name = config.provider.lower()
    if provider_name == "anthropic":
        return AnthropicProvider(
            model=config.model or "claude-sonnet-4-6-20250514",
            api_key=config.api_key,
            base_url=config.base_url,
        )
    else:
        return OpenAICompatProvider(
            provider=provider_name, model=config.model,
            api_key=config.api_key, base_url=config.base_url,
        )


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, config: AgentConfig):
        super().__init__()
        self.setWindowTitle("AI Code Agent")
        self.resize(1200, 750)
        self.setMinimumSize(800, 500)

        self.setStyleSheet("""
            QMainWindow { background: #1e1e1e; }
            QMenuBar {
                background: #2d2d2d;
                color: #ccc;
                border-bottom: 1px solid #444;
            }
            QMenuBar::item:selected { background: #094771; }
            QStatusBar {
                background: #007acc;
                color: white;
                font-size: 12px;
            }
        """)

        # Menubar
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        file_menu.addAction("Clear History", self._clear_history)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        # Central area: chat + input
        self.chat = ChatPanel()
        self.chat.set_title(
            f"AI Code Agent  |  {config.provider}  |  {config.model or 'default'}"
        )

        # Debug panel: dockable right sidebar
        self.debug = DebugPanel()
        self.debug.setVisible(True)
        self.addDockWidget(Qt.RightDockWidgetArea, self.debug)

        # Input bar
        self.input_bar = InputBar()
        self.input_bar.send_clicked.connect(self._on_send)
        self.input_bar.stop_clicked.connect(self._on_stop)

        # Assemble
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.chat)
        central_layout.addWidget(self.input_bar)
        self.setCentralWidget(central)

        # Status bar
        self._status = QStatusBar()
        self._status.showMessage(
            f"Provider: {config.provider}  |  Model: {config.model or 'default'}  |  "
            f"CWD: {config.cwd or Path.cwd()}"
        )
        self.setStatusBar(self._status)

        # Agent + worker
        registry = build_registry()
        provider = build_provider(config)
        self.agent = Agent(
            provider=provider, registry=registry,
            cwd=config.cwd,
            max_turns=config.max_turns,
            max_messages=config.max_messages,
        )
        self._worker: AgentWorker | None = None

        # Startup debug entry
        self.debug.add_entry(
            "System",
            f"Provider: {config.provider}\nModel: {config.model or 'default'}\n"
            f"Tools: Bash, FileRead, FileEdit, FileWrite, Glob, Grep\n"
            f"CWD: {config.cwd or Path.cwd()}",
            "#569cd6",
        )

        # Log file
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        self._log_path = logs_dir / f"agent_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self._log_path.write_text("", encoding="utf-8")

    def _on_send(self, text: str):
        self.chat.add_user_message(text)

        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write("\n" + "*" * 60 + "\n")
            f.write(f"User: {text}\n")
            f.write("*" * 60 + "\n\n")

        self._worker = AgentWorker(self.agent, text)
        self._worker.thinking.connect(self._on_thinking)
        self._worker.text_delta.connect(self._on_text_delta)
        self._worker.tool_use.connect(self._on_tool_use)
        self._worker.tool_done.connect(self._on_tool_done)
        self._worker.response_done.connect(self._on_response_done)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_worker_finished)

        self.input_bar.set_streaming(True)
        self._worker.start()

    def _on_stop(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()

    # ── Callbacks ─────────────────────────────────────────

    def _on_thinking(self):
        self.chat.start_streaming()

    def _on_text_delta(self, token: str):
        self.chat.append_token(token)

    def _on_tool_use(self, name: str, input_json: str, tool_use_id: str):
        input_dict = json.loads(input_json) if input_json else {}
        preview = ", ".join(
            f"{k}={str(v)[:50]!r}" for k, v in input_dict.items()
        )
        self.chat.add_tool_label(name, preview)

    def _on_tool_done(self, name: str, result: str, is_error: bool):
        color = "#f44747" if is_error else "#4ec9b0"
        preview = result[:500].replace("\n", " ")
        msg = f"Tool: {name}\nResult ({len(result)} chars): {preview}"
        self.debug.add_entry("[Tool Result]", msg, color)

    def _on_response_done(self, raw_json: str):
        raw = json.loads(raw_json) if raw_json else {}

        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write("=" * 40 + " TURN " + "=" * 40 + "\n")
            f.write("── API Request ──\n")
            f.write(json.dumps(raw.get("_request", {}), ensure_ascii=False, indent=2) + "\n\n")
            f.write("── API Response ──\n")
            resp = {k: v for k, v in raw.items() if k != "_request"}
            f.write(json.dumps(resp, ensure_ascii=False, indent=2) + "\n")
            f.write("─" * 90 + "\n")

        tool_blocks = raw.get("_tool_use_blocks", [])
        if tool_blocks:
            names = [t["tool_name"] for t in tool_blocks]
            self.debug.add_entry("Response", f"Tool calls: {', '.join(names)}", "#4ec9b0")
        else:
            self.debug.add_entry("Response", "Text response", "#4ec9b0")

        usage = raw.get("usage", {})
        self.debug.update_context_usage(usage)

    def _on_done(self, final_text: str):
        self.chat.finish_streaming()

    def _on_error(self, message: str):
        self.debug.add_entry("[Error]", message, "#f44747")

    def _on_worker_finished(self):
        self.input_bar.set_streaming(False)
        self._worker = None

    def _clear_history(self):
        self.agent.messages.clear()
        self.chat.clear()
        self.debug.clear()


def launch(config: AgentConfig):
    """Entry point for Qt mode. Creates QApplication and MainWindow."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.WindowText, QColor(212, 212, 212))
    palette.setColor(QPalette.Base, QColor(30, 30, 30))
    palette.setColor(QPalette.Text, QColor(212, 212, 212))
    palette.setColor(QPalette.Button, QColor(45, 45, 45))
    palette.setColor(QPalette.ButtonText, QColor(212, 212, 212))
    palette.setColor(QPalette.Highlight, QColor(0, 122, 204))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    window = MainWindow(config)
    window.show()
    app.exec()
