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
from prompts import build_system_prompt
from qt_ui.chat_panel import ChatPanel
from qt_ui.debug_panel import DebugPanel
from qt_ui.input_bar import InputBar
from qt_ui.agent_worker import AgentWorker
from qt_ui.config_dialog import ConfigDialog


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

        config_menu = menubar.addMenu("Config")
        config_menu.addAction("LLM", self._open_config)
        config_menu.addAction("Compact Context", self._manual_compact)

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

        # Assemble: chat fills space, input bar fixed at bottom
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.chat, stretch=1)
        central_layout.addWidget(self.input_bar, stretch=0)
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

        # Calculate fixed token counts
        sys_text = build_system_prompt(registry.get_tool_names(), str(self.agent.cwd))
        tools_json = json.dumps(registry.get_schemas(), ensure_ascii=False)
        # Token estimation: Chinese ~1.5 chars/tok, English ~4, JSON ~5
        self.debug.set_fixed_tokens(
            sys_tokens=int(len(sys_text) * 0.55),   # CN-heavy mixed
            tools_tokens=int(len(tools_json) * 0.22),  # JSON compact
        )

        # Log file — next to exe (PyInstaller) or in cwd
        if getattr(sys, 'frozen', False):
            logs_dir = Path(sys.executable).parent / "logs"
        else:
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
        # Handle /compact command
        if text.strip().lower() == "/compact":
            self._manual_compact()
            return

        self.chat.add_user_message(text)
        self.chat.show_thinking()

        # Conversation separator in log
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write("\n" + "*" * 60 + "\n")
            f.write(f"User: {text}\n")
            f.write("*" * 60 + "\n\n")

        self._worker = AgentWorker(self.agent, text)
        self._worker.thinking.connect(self._on_thinking)
        self._worker.compact.connect(self._on_compact)
        self._worker.tool_call.connect(self._on_tool_call)
        self._worker.tool_result.connect(self._on_tool_result)
        self._worker.response.connect(self._on_response)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_worker_finished)

        self.input_bar.set_busy(True)
        self._worker.start()

    # ── Callbacks ─────────────────────────────────────────

    def _on_compact(self, pre_tokens: int, post_tokens: int, trigger: str):
        self.chat.add_tool_label(
            "Compact", f"~{pre_tokens} -> ~{post_tokens} tokens ({trigger})"
        )
        self.debug.add_entry(
            "[Compact]",
            f"Trigger: {trigger}\nTokens: ~{pre_tokens} -> ~{post_tokens}",
            "#ce9178",
        )

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

    def _normalize_usage(self, usage: dict) -> dict:
        """Normalize Anthropic usage fields to OpenAI-compatible names."""
        if not usage:
            return {}
        if "prompt_tokens" not in usage and "input_tokens" in usage:
            # Anthropic: input = base + cache_creation + cache_read
            input_total = (
                (usage.get("input_tokens") or 0)
                + (usage.get("cache_creation_input_tokens") or 0)
                + (usage.get("cache_read_input_tokens") or 0)
            )
            output = usage.get("output_tokens") or 0
            cache_tokens = usage.get("cache_read_input_tokens") or 0
            return {
                "prompt_tokens": input_total,
                "completion_tokens": output,
                "total_tokens": input_total + output,
                "prompt_tokens_details": {"cached_tokens": cache_tokens},
            }
        if "total_tokens" not in usage:
            usage["total_tokens"] = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
        return usage

    def _on_response(self, raw_json: str, text: str):
        try:
            raw = json.loads(raw_json) if raw_json else {}
        except Exception:
            raw = {}

        # Preserve original for logging, normalize for display
        orig_usage = raw.get("usage", {})
        norm_usage = self._normalize_usage(orig_usage)

        # Log full request + response (original data, not normalized)
        req = raw.get("_request", {})
        resp = {k: v for k, v in raw.items() if k not in ("_request", "_tool_use_blocks")}
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write("=" * 40 + " TURN " + "=" * 40 + "\n")
            f.write("── API Request ──\n")
            f.write(json.dumps(req, ensure_ascii=False, indent=2) + "\n\n")
            f.write("── API Response ──\n")
            f.write(json.dumps(resp, ensure_ascii=False, indent=2) + "\n")
            f.write("─" * 90 + "\n")

        # Show request summary in debug
        msgs = req.get("messages", [])
        sys_text = req.get("system", "")  # Anthropic puts system prompt here
        msg_parts = [f"Model: {req.get('model', '?')}  |  Messages: {len(msgs)}"]
        if sys_text:
            msg_parts.append(f"  system: ({len(str(sys_text))} chars)")
        for i, m in enumerate(msgs):
            role = m.get("role", "?")
            raw_content = m.get("content", "")
            # Handle Anthropic list-of-blocks content format
            if isinstance(raw_content, list):
                parts = []
                for block in raw_content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            parts.append(str(block.get("text", "")))
                        elif block.get("type") == "tool_result":
                            parts.append(f"[tool_result]")
                        elif block.get("type") == "tool_use":
                            parts.append(f"[tool_use:{block.get('name','')}]")
                raw_content = " ".join(parts)
            if role == "system":
                msg_parts.append(f"  [{i}] system ({len(str(raw_content))} chars)")
            elif role == "tool":
                cid = m.get("tool_call_id", "")
                preview = str(raw_content)[:100].replace("\n", " ")
                msg_parts.append(f"  [{i}] tool({cid}): {preview}")
            else:
                preview = str(raw_content)[:150].replace("\n", " ").strip()
                msg_parts.append(f"  [{i}] {role}: {preview}")
        self.debug.add_entry("[Request]", "\n".join(msg_parts), "#569cd6")

        # Show response in debug
        tool_blocks = raw.get("_tool_use_blocks", [])
        prompt_tokens = norm_usage.get("prompt_tokens", "?")
        completion_tokens = norm_usage.get("completion_tokens", "?")

        if tool_blocks:
            names = [t["tool_name"] for t in tool_blocks]
            self.debug.add_entry(
                "[Response]",
                f"Tool calls: {', '.join(names)}\n"
                f"prompt={prompt_tokens}, completion={completion_tokens}",
                "#4ec9b0",
            )
        else:
            self.debug.add_entry(
                "[Response]",
                f"Text:\n{text}\n\n"
                f"prompt={prompt_tokens}, completion={completion_tokens}",
                "#4ec9b0",
            )

        self.debug.update_context_usage(norm_usage)

    def _on_done(self, final_text: str):
        self.chat.hide_thinking()
        if final_text and not final_text.startswith("Error:"):
            self.chat.add_assistant_message(final_text)

    def _on_error(self, message: str):
        self.debug.add_entry("[Error]", message, "#f44747")

    def _on_worker_finished(self):
        self.input_bar.set_busy(False)
        self._worker = None

    def _open_config(self):
        dlg = ConfigDialog(self)
        if dlg.exec() == ConfigDialog.Accepted:
            # Reload config and rebuild agent
            new_config = AgentConfig.from_yaml()
            self.agent.provider = build_provider(new_config)
            self.agent.messages.clear()
            self.chat.clear()
            self.debug.clear()
            self.chat.set_title(
                f"AI Code Agent  |  {new_config.provider}  |  {new_config.model or 'default'}"
            )
            self._status.showMessage(
                f"Provider: {new_config.provider}  |  Model: {new_config.model or 'default'}  |  "
                f"CWD: {new_config.cwd or Path.cwd()}"
            )
            self.debug.add_entry(
                "System",
                f"Config updated: {new_config.provider} / {new_config.model}",
                "#569cd6",
            )

    def _manual_compact(self):
        """Manually compact conversation context."""
        import asyncio
        import threading

        self.chat.show_thinking()
        main_window = self  # capture for thread

        def _run_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                pre, post, status = loop.run_until_complete(
                    main_window._do_compact()
                )
            except Exception as e:
                pre, post, status = 0, 0, f"thread error: {e}"
            finally:
                loop.close()

            # Schedule UI update on main thread
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: main_window._on_compact_done(
                pre, post, status
            ))

        threading.Thread(target=_run_in_thread, daemon=True).start()

    async def _do_compact(self):
        """Async compaction logic."""
        from compact.compact import compact_conversation
        from compact.grouping import estimate_tokens

        pre = estimate_tokens(self.agent.messages)
        try:
            result = await compact_conversation(
                self.agent.provider,
                self.agent.messages,
                self.agent.registry.get_schemas(),
                keep_recent_rounds=2,
            )
            if result.summary_messages:
                self.agent.messages = result.summary_messages + result.messages_to_keep
                self.agent._compact_count += 1
                return pre, result.post_tokens, f"manual (#{self.agent._compact_count})"
            else:
                return pre, pre, "skipped (not enough messages)"
        except Exception as e:
            return pre, pre, f"failed: {e}"

    def _on_compact_done(self, pre: int, post: int, status: str):
        """Callback from compaction thread — runs on main thread."""
        self._on_compact(pre, post, status)
        self.chat.hide_thinking()

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
