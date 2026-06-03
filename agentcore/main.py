"""Entry point for My Agent.

python main.py                  Qt 桌面界面 (默认)
python main.py -s               终端交互模式
python main.py -c "message"     单次命令行模式
"""

import asyncio
import sys

from agentcore.config import AgentConfig
from agentcore.tools.registry import ToolRegistry
from agentcore.tools.bash import BashTool
from agentcore.tools.file_read import FileReadTool
from agentcore.tools.file_edit import FileEditTool
from agentcore.tools.file_write import FileWriteTool
from agentcore.tools.glob import GlobTool
from agentcore.tools.grep import GrepTool
from agentcore.providers.anthropic import AnthropicProvider
from agentcore.providers.openai_compat import OpenAICompatProvider
from agentcore.agent import Agent


def build_registry() -> tuple[ToolRegistry, str]:
    from agentcore.skills.loader import load_skills
    from agentcore.skills.skill_tool import SkillTool

    skills = load_skills()
    skill_tool = SkillTool(skills)
    skills_text = skill_tool.get_skill_list()

    registry = ToolRegistry()
    tools = [BashTool(), FileReadTool(), FileEditTool(),
             FileWriteTool(), GlobTool(), GrepTool()]
    if skills:
        tools.append(skill_tool)
    registry.register_all(tools)
    return registry, skills_text


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
    registry, skills_text = build_registry()
    provider = build_provider(config)
    agent = Agent(
        provider=provider, registry=registry, cwd=config.cwd,
        max_turns=config.max_turns, max_messages=config.max_messages,
        on_thinking=_on_thinking,
        on_tool_call=_on_tool_call,
        on_tool_result=_on_tool_result,
    )
    agent.skills_text = skills_text
    print("Working...", flush=True)
    result = await agent.run(user_message)
    print(f"\n{'─' * 60}")
    print(result)
    print(f"{'─' * 60}")


async def run_interactive(config: AgentConfig):
    registry, skills_text = build_registry()
    provider = build_provider(config)
    agent = Agent(
        provider=provider, registry=registry, cwd=config.cwd,
        max_turns=config.max_turns, max_messages=config.max_messages,
        on_thinking=_on_thinking,
        on_tool_call=_on_tool_call,
        on_tool_result=_on_tool_result,
    )
    agent.skills_text = skills_text

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

    if "--ws" in sys.argv:
        from agentcore.ws_server import run_ws_server
        port_idx = sys.argv.index("--port") if "--port" in sys.argv else -1
        port = int(sys.argv[port_idx + 1]) if port_idx != -1 else 18765
        await run_ws_server(config, port)
        return

    if len(sys.argv) >= 3 and sys.argv[1] == "-c":
        await run_one_shot(config, " ".join(sys.argv[2:]))
    elif len(sys.argv) >= 2 and sys.argv[1] == "-s":
        await run_interactive(config)
    elif len(sys.argv) >= 2 and sys.argv[1] not in ("-s", "-c"):
        await run_one_shot(config, " ".join(sys.argv[1:]))
    else:
        # Flet mode — handled in __name__ == "__main__"
        pass


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Default: launch Flet GUI
        from agentcore.flet_ui.app import launch_flet
        launch_flet(AgentConfig.from_yaml())
    else:
        asyncio.run(main())
