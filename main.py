"""Entry point for My Agent.

python main.py                  Qt 桌面界面 (默认)
python main.py -s               终端交互模式
python main.py -c "message"     单次命令行模式
"""

import asyncio
import sys

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


_thinking_phase = 0
_spinner_chars = "|/-\\"


async def _on_thinking():
    global _thinking_phase
    _thinking_phase = 0
    # Start spinner
    async def spin():
        global _thinking_phase
        for c in _spinner_chars:
            if _thinking_phase != 0:
                break
            print(f"\r  {c} thinking...", end="", flush=True)
            await asyncio.sleep(0.08)
    asyncio.create_task(spin())


async def _on_tool_call(name: str, input: dict):
    global _thinking_phase
    _thinking_phase = 1
    preview = ", ".join(
        f"{k}={str(v)[:50]!r}" for k, v in input.items()
    )
    print(f"\r  🔧 {name}({preview})")
    _thinking_phase = 0


async def _on_tool_result(name: str, result: str, is_error: bool):
    preview = result[:100].replace("\n", " ")
    print(f"\r  → {preview}")


async def run_one_shot(config: AgentConfig, user_message: str):
    registry = build_registry()
    provider = build_provider(config)
    agent = Agent(
        provider=provider, registry=registry, cwd=config.cwd,
        max_turns=config.max_turns, max_messages=config.max_messages,
        on_thinking=_on_thinking,
        on_tool_call=_on_tool_call,
        on_tool_result=_on_tool_result,
    )
    print("Working...", flush=True)
    result = await agent.run(user_message)
    print(f"\n{'─' * 60}")
    print(result)
    print(f"{'─' * 60}")


async def run_interactive(config: AgentConfig):
    registry = build_registry()
    provider = build_provider(config)
    agent = Agent(
        provider=provider, registry=registry, cwd=config.cwd,
        max_turns=config.max_turns, max_messages=config.max_messages,
        on_thinking=_on_thinking,
        on_tool_call=_on_tool_call,
        on_tool_result=_on_tool_result,
    )

    print()
    print(f"  Provider: {config.provider}  |  Model: {provider.model}")
    print(f"  Tools: {', '.join(registry.get_tool_names())}")
    print(f"  /exit 退出  /clear 清除历史")
    print()

    while True:
        try:
            user_input = input("You > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("/exit", "/quit"):
            print("Goodbye!")
            break
        if user_input.lower() == "/clear":
            agent.messages.clear()
            print("[History cleared]\n")
            continue

        try:
            result = await agent.run(user_input)
            print(f"\n{result}\n")
        except Exception as e:
            print(f"\n[Error] {e}\n")


async def main():
    config = AgentConfig.from_yaml()

    if len(sys.argv) >= 3 and sys.argv[1] == "-c":
        await run_one_shot(config, " ".join(sys.argv[2:]))
    elif len(sys.argv) >= 2 and sys.argv[1] == "-s":
        await run_interactive(config)
    elif len(sys.argv) >= 2 and sys.argv[1] not in ("-s", "-c"):
        await run_one_shot(config, " ".join(sys.argv[1:]))
    else:
        # Qt mode — handled in __name__ == "__main__"
        pass


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Default: launch Qt GUI
        from qt_ui.main_window import launch
        launch(AgentConfig.from_yaml())
    else:
        asyncio.run(main())
