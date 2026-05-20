"""Agent core loop — mirrors query.ts while(true) with needsFollowUp termination."""

import json
from pathlib import Path
from typing import Callable, Awaitable
from core_types import Message
from tools.base import ToolContext
from tools.registry import ToolRegistry
from providers.base import BaseProvider
from prompts import build_system_prompt

# Callback types
OnThinking = Callable[[], Awaitable[None]]
OnToolCall = Callable[[str, dict], Awaitable[None]]
OnToolResult = Callable[[str, str, bool], Awaitable[None]]
OnResponse = Callable[[str, list, dict], Awaitable[None]]  # text, tool_use_blocks, raw_response


class Agent:
    """
    Agent session — mirrors QueryEngine.ts + query.ts.

    One Agent per conversation. Each run() call processes one user message
    through the while-True agent loop. Messages persist across run() calls.
    """

    def __init__(
        self,
        provider: BaseProvider,
        registry: ToolRegistry,
        cwd: str | None = None,
        max_turns: int = 50,
        max_messages: int = 200,
        on_thinking: OnThinking | None = None,
        on_tool_call: OnToolCall | None = None,
        on_tool_result: OnToolResult | None = None,
        on_response: OnResponse | None = None,
    ):
        self.provider = provider
        self.registry = registry
        self.cwd = Path(cwd) if cwd else Path.cwd()
        self.max_turns = max_turns
        self.max_messages = max_messages
        self.messages: list[Message] = []
        self.on_thinking = on_thinking
        self.on_tool_call = on_tool_call
        self.on_tool_result = on_tool_result
        self.on_response = on_response

    async def run(self, user_message: str) -> str:
        """Process one user message. May involve multiple LLM↔tool rounds."""
        self.messages.append(Message(role="user", content=user_message))

        turn_count = 0
        while turn_count < self.max_turns:
            turn_count += 1

            # Simple message cap — keep last N messages (naive snip)
            if len(self.messages) > self.max_messages:
                self.messages = self.messages[-self.max_messages:]

            # 1. Call LLM — get assistant response + tool_use blocks
            tools_schema = self.registry.get_schemas()
            system_prompt = build_system_prompt(
                self.registry.get_tool_names(),
                str(self.cwd),
            )

            if self.on_thinking:
                await self.on_thinking()

            try:
                assistant_msg, tool_use_blocks, raw_response = await self.provider.call(
                    messages=self.messages,
                    tools=tools_schema,
                    system=system_prompt,
                )
            except Exception as e:
                error_msg = Message(
                    role="assistant",
                    content=f"Error calling LLM: {e}",
                )
                self.messages.append(error_msg)
                return error_msg.content

            self.messages.append(assistant_msg)

            if self.on_response:
                await self.on_response(
                    assistant_msg.content or "",
                    tool_use_blocks,
                    raw_response,
                )

            # 2. Termination check — mirrors query.ts:1062
            if not tool_use_blocks:
                return assistant_msg.content or "(no response)"

            # 3. Execute tools — mirrors query.ts:1366
            context = ToolContext(cwd=self.cwd, messages=list(self.messages))
            for block in tool_use_blocks:
                if self.on_tool_call:
                    await self.on_tool_call(block.tool_name, block.input)

                tool = self.registry.get(block.tool_name)
                if tool is None:
                    result_text = json.dumps({
                        "error": f"Unknown tool: {block.tool_name}"
                    })
                    is_error = True
                else:
                    try:
                        result_text = await tool.call(block.input, context)
                        is_error = False
                    except Exception as e:
                        result_text = f"Tool error: {e}"
                        is_error = True

                if self.on_tool_result:
                    await self.on_tool_result(block.tool_name, result_text, is_error)

                self.messages.append(Message(
                    role="user",
                    content=result_text,
                    tool_use_id=block.tool_use_id,
                ))

        return "Agent: max turns reached without completing the task."

    async def run_stream(self, user_message: str):
        """Streaming version of run(). Yields events instead of returning text."""
        from events import (
            ThinkingEvent, TextDeltaEvent, ToolUseEvent, ToolDoneEvent,
            ResponseDoneEvent, DoneEvent, ErrorEvent,
        )

        self.messages.append(Message(role="user", content=user_message))

        turn_count = 0
        while turn_count < self.max_turns:
            turn_count += 1

            if len(self.messages) > self.max_messages:
                self.messages = self.messages[-self.max_messages:]

            tools_schema = self.registry.get_schemas()
            system_prompt = build_system_prompt(
                self.registry.get_tool_names(),
                str(self.cwd),
            )

            yield ThinkingEvent()

            text_parts: list[str] = []
            tool_use_blocks: list[ToolUseBlock] = []
            raw_response: dict = {}

            try:
                async for event in self.provider.call_stream(
                    messages=self.messages,
                    tools=tools_schema,
                    system=system_prompt,
                ):
                    if isinstance(event, TextDeltaEvent):
                        text_parts.append(event.token)
                        yield event
                    elif isinstance(event, ToolUseEvent):
                        block = ToolUseBlock(
                            tool_use_id=event.tool_use_id,
                            tool_name=event.tool_name,
                            input=event.input,
                        )
                        tool_use_blocks.append(block)
                        yield event
                    elif isinstance(event, ResponseDoneEvent):
                        raw_response = event.raw
                        yield event
                    elif isinstance(event, ErrorEvent):
                        self.messages.append(Message(
                            role="assistant",
                            content=f"Error: {event.message}",
                        ))
                        yield event
                        yield DoneEvent(final_text=f"Error: {event.message}")
                        return
            except Exception as e:
                yield ErrorEvent(message=str(e))
                yield DoneEvent(final_text=f"Error: {e}")
                return

            assistant_text = "".join(text_parts)
            assistant_msg = Message(
                role="assistant",
                content=assistant_text,
                tool_use_blocks=tool_use_blocks,
            )
            self.messages.append(assistant_msg)

            # Termination check
            if not tool_use_blocks:
                yield DoneEvent(final_text=assistant_text or "(no response)")
                return

            # Execute tools
            context = ToolContext(cwd=self.cwd, messages=list(self.messages))
            for block in tool_use_blocks:
                tool = self.registry.get(block.tool_name)
                if tool is None:
                    result_text = json.dumps({"error": f"Unknown tool: {block.tool_name}"})
                    is_error = True
                else:
                    try:
                        result_text = await tool.call(block.input, context)
                        is_error = False
                    except Exception as e:
                        result_text = f"Tool error: {e}"
                        is_error = True

                yield ToolDoneEvent(
                    tool_name=block.tool_name,
                    result=result_text,
                    is_error=is_error,
                )

                self.messages.append(Message(
                    role="user",
                    content=result_text,
                    tool_use_id=block.tool_use_id,
                ))

        yield DoneEvent(final_text="Agent: max turns reached without completing the task.")
