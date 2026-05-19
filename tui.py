"""Two-panel TUI: left = chat, right = raw API messages."""

import json
from datetime import datetime

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Input, Static, Header, Footer
from textual.reactive import reactive

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


class DebugPanel(VerticalScroll):
    """Right panel: raw API request/response log."""

    def add_entry(self, title: str, content: str, color: str = "white"):
        ts = datetime.now().strftime("%H:%M:%S")
        self.mount(Static(
            f"[bold {color}]{ts}  {title}[/]\n{content}\n",
        ))
        self.scroll_end(animate=False)


class ChatPanel(VerticalScroll):
    """Left panel: chat messages."""

    def add_user(self, text: str):
        self.mount(Static(
            f"[bold cyan]You[/]\n{text}\n",
        ))
        self.scroll_end(animate=False)

    def add_agent_text(self, text: str):
        self.mount(Static(
            f"[bold green]Agent[/]\n{text}\n",
        ))
        self.scroll_end(animate=False)

    def add_thinking(self):
        self.mount(Static(
            "[dim italic]  thinking...[/]\n",
        ))
        self.scroll_end(animate=False)

    def add_tool_call(self, name: str, input: dict):
        preview = self._format_input(input)
        self.mount(Static(
            f"[bold yellow]  🔧 {name}[/] [dim]({preview})[/]\n",
        ))
        self.scroll_end(animate=False)

    def add_tool_result(self, name: str, result: str, is_error: bool):
        preview = result[:200].replace("\n", " ") + ("..." if len(result) > 200 else "")
        color = "red" if is_error else "dim"
        self.mount(Static(
            f"  [{color}]→ {preview}[/]\n",
        ))
        self.scroll_end(animate=False)

    @staticmethod
    def _format_input(input: dict) -> str:
        parts = []
        for k, v in input.items():
            if isinstance(v, str):
                if len(v) > 50:
                    v = v[:47] + "..."
                parts.append(f"{k}={v!r}")
            else:
                parts.append(f"{k}={v}")
        return ", ".join(parts)


class MyAgentApp(App):
    """Two-panel agent TUI."""

    CSS = """
    Horizontal { height: 1fr; }
    ChatPanel {
        width: 1fr;
        border: solid green;
        padding: 1;
    }
    DebugPanel {
        width: 1fr;
        border: solid $accent;
        padding: 1;
    }
    Input {
        dock: bottom;
        margin: 1;
    }
    """

    TITLE = "My Agent"
    SUB_TITLE = "Ctrl+Q to quit"

    agent: Agent
    debug: DebugPanel
    chat: ChatPanel

    def compose(self) -> ComposeResult:
        yield Header()
        yield Horizontal(
            ChatPanel(id="chat"),
            DebugPanel(id="debug"),
        )
        yield Input(placeholder="Type your message here...  (Ctrl+Q to quit)")

    def on_mount(self):
        config = AgentConfig.from_yaml()
        registry = build_registry()
        provider = build_provider(config)

        self.chat = self.query_one("#chat", ChatPanel)
        self.debug = self.query_one("#debug", DebugPanel)

        self.agent = Agent(
            provider=provider, registry=registry,
            cwd=config.cwd,
            max_turns=config.max_turns, max_messages=config.max_messages,
            on_thinking=self._on_thinking,
            on_tool_call=self._on_tool_call,
            on_tool_result=self._on_tool_result,
        )

        self.debug.add_entry("System", (
            f"Provider: {config.provider}\n"
            f"Model: {provider.model}\n"
            f"Tools: {registry.get_tool_names()}\n"
            f"CWD: {self.agent.cwd}"
        ), "blue")

    @on(Input.Submitted)
    async def on_input(self, event: Input.Submitted):
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""

        if text.lower() in ("/exit", "/quit"):
            self.exit()
            return
        if text.lower() == "/clear":
            self.agent.messages.clear()
            self.chat.mount(Static("[dim]── History cleared ──[/]\n"))
            return

        self.chat.add_user(text)

        try:
            result = await self.agent.run(text)
            self.chat.add_agent_text(result)
        except Exception as e:
            self.chat.add_agent_text(f"[Error] {e}")

    # ── Agent callbacks ──────────────────────────────────────

    async def _on_thinking(self):
        # Build and show the outgoing request
        msgs = self.agent.messages
        tools = self.agent.registry.get_schemas()

        sys_prompt = (
            f"[System prompt: {len(repr(self.agent.provider))} chars]\n"
        )
        msg_list = []
        for i, m in enumerate(msgs):
            role = m.role
            if m.is_tool_result:
                preview = m.content[:150].replace("\n", " ")
                msg_list.append(f"  [{i}] tool_result({m.tool_use_id}): {preview}...")
            elif m.has_tool_uses:
                names = [t.tool_name for t in m.tool_use_blocks]
                msg_list.append(f"  [{i}] assistant → {names}")
            else:
                preview = m.content[:100].replace("\n", " ")
                msg_list.append(f"  [{i}] {role}: {preview}")

        tool_list = [f"  {t['name']}: {t['description'][:80]}" for t in tools]

        debug_text = (
            f"{sys_prompt}\n"
            f"Messages ({len(msgs)}):\n" + "\n".join(msg_list) + "\n\n"
            f"Tools ({len(tools)}):\n" + "\n".join(tool_list)
        )

        self.app.call_from_thread(
            lambda: self.debug.add_entry("📤 Request", debug_text, "blue")
        )
        self.app.call_from_thread(lambda: self.chat.add_thinking())

    async def _on_tool_call(self, name: str, input: dict):
        self.app.call_from_thread(
            lambda: self.chat.add_tool_call(name, input)
        )

    async def _on_tool_result(self, name: str, result: str, is_error: bool):
        self.app.call_from_thread(
            lambda: self.chat.add_tool_result(name, result, is_error)
        )
        color = "red" if is_error else "green"
        preview = result[:500].replace("\n", "\n  ")
        msg = f"Tool: {name}\nResult ({len(result)} chars):\n  {preview}"
        self.app.call_from_thread(
            lambda: self.debug.add_entry(f"📥 Tool Result", msg, color)
        )


def main():
    app = MyAgentApp()
    app.run()


if __name__ == "__main__":
    main()
