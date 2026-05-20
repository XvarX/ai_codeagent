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

        # Central: chat + input
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

        # Agent
        registry = build_registry()
        provider = build_provider(config)
        self.agent = Agent(
            provider=provider, registry=registry,
            cwd=config.cwd,
            max_turns=config.max_turns,
            max_messages=config.max_messages,
        )
        self._worker: AgentWorker | None = None

        # Log file
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        self._log_path = logs_dir / f"agent_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self._log_path.write_text("", encoding="utf-8")

        # Startup debug entry
        self.debug.add_entry(
            "System",
            f"Provider: {config.provider}\nModel: {config.model or 'default'}\n"
            f"Tools: Bash, FileRead, FileEdit, FileWrite, Glob, Grep\n"
            f"CWD: {config.cwd or Path.cwd()}",
            "#569cd6",
        )

    def _on_send(self, text: str):
        self.chat.add_user_message(text)
        self.chat.show_thinking()

        # Conversation separator in log
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write("\n" + "*" * 60 + "\n")
            f.write(f"User: {text}\n")
            f.write("*" * 60 + "\n\n")

        self._worker = AgentWorker(self.agent, text)
        self._worker.thinking.connect(self._on_thinking)
        self._worker.tool_call.connect(self._on_tool_call)
        self._worker.tool_result.connect(self._on_tool_result)
        self._worker.response.connect(self._on_response)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_worker_finished)

        self.input_bar.set_busy(True)
        self._worker.start()

    # ── Callbacks ─────────────────────────────────────────

    def _on_thinking(self):
        pass  # thinking label already shown by _on_send

    def _on_tool_call(self, name: str, input_json: str):
        input_dict = json.loads(input_json) if input_json else {}
        preview = ", ".join(
            f"{k}={str(v)[:50]!r}" for k, v in input_dict.items()
        )
        self.chat.add_tool_label(name, preview)

    def _on_tool_result(self, name: str, result: str, is_error: bool):
        color = "#f44747" if is_error else "#4ec9b0"
        preview = result[:500].replace("\n", " ")
        msg = f"Tool: {name}\nResult ({len(result)} chars): {preview}"
        self.debug.add_entry("[Tool Result]", msg, color)

    def _on_response(self, raw_json: str, text: str):
        raw = json.loads(raw_json) if raw_json else {}

        # Log full request + response
        req = raw.get("_request", {})
        resp = {k: v for k, v in raw.items() if k not in ("_request", "_tool_use_blocks")}
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write("=" * 40 + " TURN " + "=" * 40 + "\n")
            f.write("── API Request ──\n")
            f.write(json.dumps(req, ensure_ascii=False, indent=2) + "\n\n")
            f.write("── API Response ──\n")
            f.write(json.dumps(resp, ensure_ascii=False, indent=2) + "\n")
            f.write("─" * 90 + "\n")

        # Show request in debug
        self.debug.add_entry(
            "[Request]",
            f"Model: {req.get('model', '?')}\nMessages: {len(req.get('messages', []))}\n"
            f"Tools: {len(req.get('tools', []) or [])}",
            "#569cd6",
        )

        # Show response in debug
        tool_blocks = raw.get("_tool_use_blocks", [])
        usage = raw.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", "?")
        completion_tokens = usage.get("completion_tokens", "?")

        if tool_blocks:
            names = [t["tool_name"] for t in tool_blocks]
            self.debug.add_entry(
                "[Response]",
                f"Tool calls: {', '.join(names)}\n"
                f"prompt={prompt_tokens}, completion={completion_tokens}",
                "#4ec9b0",
            )
        else:
            text_preview = text[:300] if text else "(empty)"
            self.debug.add_entry(
                "[Response]",
                f"Text: {text_preview}\n"
                f"prompt={prompt_tokens}, completion={completion_tokens}",
                "#4ec9b0",
            )

        self.debug.update_context_usage(usage)

    def _on_done(self, final_text: str):
        self.chat.hide_thinking()
        if final_text and not final_text.startswith("Error:"):
            self.chat.add_assistant_message(final_text)

    def _on_error(self, message: str):
        self.debug.add_entry("[Error]", message, "#f44747")

    def _on_worker_finished(self):
        self.input_bar.set_busy(False)
        self._worker = None

    def _clear_history(self):
        self.agent.messages.clear()
        self.chat.clear()
        self.debug.clear()


def launch(config: AgentConfig):
    """Entry point for Qt mode."""
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
