"""Agent core loop — mirrors query.ts while(true) with needsFollowUp termination."""

import json
from pathlib import Path
from typing import Callable, Awaitable
from core_types import Message, ToolUseBlock
from tools.base import ToolContext
from tools.registry import ToolRegistry
from tools.tool_result_storage import (
    process_tool_result_block,
    apply_tool_result_budget,
    ContentReplacementState,
)
from providers.base import BaseProvider
from prompts import build_system_prompt

# Callback types
OnThinking = Callable[[], Awaitable[None]]
OnToolCall = Callable[[str, dict], Awaitable[None]]
OnToolResult = Callable[[str, str, bool], Awaitable[None]]
OnResponse = Callable[[str, list, dict], Awaitable[None]]  # text, tool_use_blocks, raw_response
OnCompact = Callable[[int, int, str], Awaitable[None]]  # pre_tokens, post_tokens, trigger


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
        on_compact: OnCompact | None = None,
        context_window: int = 128000,
        compact_threshold: float = 0.85,
        reserved_output: int = 8000,
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
        self.on_compact = on_compact
        self._compact_count = 0
        self.context_window = context_window
        self.compact_threshold = compact_threshold
        self.reserved_output = reserved_output
        self._last_actual_tokens = 0
        self._replacement_state = ContentReplacementState()

    def snip_keep_last(self, keep_groups: int = 1) -> tuple[int, int, int]:
        """Snip: keep only the last keep_groups API-rounds. Returns (before, after, removed)."""
        from compact.grouping import estimate_tokens_with_usage, group_by_api_round
        groups = group_by_api_round(self.messages)
        pre = len(self.messages)
        pre_tok = estimate_tokens_with_usage(self.messages)
        if len(groups) > keep_groups:
            kept = groups[-keep_groups:]
            # Ensure first message of kept groups is a non-tool-result user message
            first_group = kept[0]
            first_user = next((i for i, m in enumerate(first_group) if m.role == "user" and not m.is_tool_result), 0)
            self.messages = first_group[first_user:] + [m for g in kept[1:] for m in g]
        post_tok = estimate_tokens_with_usage(self.messages)
        return pre_tok, post_tok, pre - len(self.messages)

    async def run(self, user_message: str) -> str:
        """Process one user message. May involve multiple LLM↔tool rounds."""
        self.messages.append(Message(role="user", content=user_message))

        turn_count = 0
        while turn_count < self.max_turns:
            turn_count += 1

            # ── Compaction Pipeline (mirrors query.ts) ──────────

            # Micro-compact — trim old tool results
            if turn_count > 1:
                from compact.microCompact import micro_compact
                micro_compact(self.messages)

            # Auto-compact — use actual tokens from last API call as base
            from compact.autoCompact import should_auto_compact
            if should_auto_compact(
                self.messages,
                getattr(self.provider, 'model', None),
                threshold=self.compact_threshold,
                actual_base=self._last_actual_tokens,
                context_window=self.context_window,
                reserved_output=self.reserved_output,
            ):
                from compact.compact import compact_conversation
                from events import CompactCallEvent
                pre_tokens = self.est_tokens()
                pre_count = len(self.messages)
                try:
                    result = await compact_conversation(
                        self.provider, self.messages,
                        self.registry.get_schemas(),
                        keep_recent_rounds=2,
                    )
                    # Replace messages with compacted version
                    self.messages = result.summary_messages + result.messages_to_keep
                    self._last_actual_tokens = result.post_tokens
                    self._compact_count += 1

                    if self.on_compact:
                        await self.on_compact(
                            pre_tokens, result.post_tokens,
                            f"auto (#{self._compact_count})"
                        )
                except Exception:
                    pass  # compaction failure is non-fatal

            # Layer 2: Per-message tool result budget before LLM call
            self.messages = apply_tool_result_budget(
                self.messages, self._replacement_state, self.cwd)

            # Snip: drop oldest API-round groups until within context window
            from compact.grouping import estimate_tokens_with_usage, group_by_api_round
            limit = self.context_window - self.reserved_output
            groups = group_by_api_round(self.messages)
            orig_count = len(groups)
            pre_tokens = estimate_tokens_with_usage(self.messages)
            while len(groups) > 1:
                total = estimate_tokens_with_usage(self.messages)
                if total <= limit:
                    break
                groups.pop(0)
                self.messages = [m for g in groups for m in g]
            removed_groups = orig_count - len(groups)
            if removed_groups > 0 and self.on_compact:
                post_tokens = estimate_tokens_with_usage(self.messages)
                await self.on_compact(pre_tokens, post_tokens,
                    f"snip {removed_groups} groups")

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
                assistant_msg.id = raw_response.get("id")
                assistant_msg.usage = raw_response.get("usage", {})
            except Exception as e:
                err_str = str(e)
                # Reactive compact on prompt-too-long (413)
                if "413" in err_str or "prompt_too_long" in err_str or "too long" in err_str.lower():
                    self._reactive_compact()
                    if self.on_compact:
                        await self.on_compact(
                            self.est_tokens(), self.est_tokens(),
                            "reactive (413)"
                        )
                    # Retry after compact
                    try:
                        assistant_msg, tool_use_blocks, raw_response = await self.provider.call(
                            messages=self.messages,
                            tools=tools_schema,
                            system=system_prompt,
                        )
                        assistant_msg.id = raw_response.get("id")
                        assistant_msg.usage = raw_response.get("usage", {})
                    except Exception as e2:
                        error_msg = Message(
                            role="assistant",
                            content=f"Error calling LLM after compaction: {e2}",
                        )
                        self.messages.append(error_msg)
                        return error_msg.content
                else:
                    error_msg = Message(
                        role="assistant",
                        content=f"Error calling LLM: {e}",
                    )
                    self.messages.append(error_msg)
                    return error_msg.content

            self.messages.append(assistant_msg)

            # Track actual token usage from API response
            usage = raw_response.get("usage", {})
            if usage.get("total_tokens"):
                self._last_actual_tokens = usage["total_tokens"]
            elif usage.get("input_tokens"):
                self._last_actual_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

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
                        # Layer 1: Per-tool persistence threshold
                        result_text = process_tool_result_block(
                            result_text,
                            tool.name,
                            block.tool_use_id,
                            getattr(tool, 'max_result_chars', None),
                            self.cwd,
                        )
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

    def est_tokens(self) -> int:
        from compact.grouping import estimate_tokens
        return estimate_tokens(self.messages)

    def _reactive_compact(self):
        from compact.grouping import group_by_api_round
        groups = group_by_api_round(self.messages)
        if len(groups) <= 2:
            return
        keep = max(2, len(groups) // 2)
        self.messages = [m for g in groups[-keep:] for m in g]

    async def run_stream(self, user_message: str):
        """Streaming version of run(). Yields events instead of returning text."""
        from events import (
            ThinkingEvent, TextDeltaEvent, ToolUseEvent, ToolDoneEvent,
            ResponseDoneEvent, DoneEvent, ErrorEvent, CompactEvent, SnipEvent,
        )

        self.messages.append(Message(role="user", content=user_message))

        turn_count = 0
        while turn_count < self.max_turns:
            turn_count += 1

            # ── Compaction Pipeline (mirrors run()) ──────────
            if turn_count > 1:
                from compact.microCompact import micro_compact
                micro_compact(self.messages)

            from compact.autoCompact import should_auto_compact
            if should_auto_compact(
                self.messages,
                getattr(self.provider, 'model', None),
                threshold=self.compact_threshold,
                actual_base=self._last_actual_tokens,
                context_window=self.context_window,
                reserved_output=self.reserved_output,
            ):
                from compact.compact import compact_conversation
                from events import CompactCallEvent
                pre_tokens = self.est_tokens()
                pre_count = len(self.messages)
                yield CompactCallEvent(
                    old_msg_count=pre_count,
                    pre_tokens=pre_tokens,
                )
                try:
                    result = await compact_conversation(
                        self.provider, self.messages,
                        self.registry.get_schemas(),
                        keep_recent_rounds=2,
                    )
                    self.messages = result.summary_messages + result.messages_to_keep
                    self._last_actual_tokens = result.post_tokens
                    self._compact_count += 1

                    yield CompactEvent(
                        pre_tokens=pre_tokens,
                        post_tokens=result.post_tokens,
                        trigger=f"auto (#{self._compact_count})",
                        summary=result.summary_text,
                    )
                except Exception:
                    yield CompactEvent(
                        pre_tokens=pre_tokens,
                        post_tokens=pre_tokens,
                        trigger=f"auto (#{self._compact_count}) — failed",
                    )

            # Layer 2: Per-message tool result budget before LLM call
            self.messages = apply_tool_result_budget(
                self.messages, self._replacement_state, self.cwd)

            # Snip: drop oldest API-round groups until within context window
            from compact.grouping import estimate_tokens_with_usage, group_by_api_round
            limit = self.context_window - self.reserved_output
            groups = group_by_api_round(self.messages)
            orig_count = len(groups)
            pre_tokens = estimate_tokens_with_usage(self.messages)
            while len(groups) > 1:
                total = estimate_tokens_with_usage(self.messages)
                if total <= limit:
                    break
                groups.pop(0)
                self.messages = [m for g in groups for m in g]
            removed_groups = orig_count - len(groups)
            if removed_groups > 0:
                post_tokens = estimate_tokens_with_usage(self.messages)
                yield SnipEvent(
                    groups_removed=removed_groups,
                    messages_removed=0,  # rough, not counting
                    tokens_before=pre_tokens,
                    tokens_after=post_tokens,
                )

            tools_schema = self.registry.get_schemas()
            system_prompt = build_system_prompt(
                self.registry.get_tool_names(),
                str(self.cwd),
            )

            yield ThinkingEvent()

            text_parts: list[str] = []
            tool_use_blocks: list[ToolUseBlock] = []

            try:
                async for event in self.provider.call_stream(
                    messages=self.messages,
                    tools=tools_schema,
                    system=system_prompt,
                ):
                    if isinstance(event, TextDeltaEvent):
                        if not event.reasoning:
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
                        # Track actual token usage
                        usage = event.raw.get("usage", {})
                        if usage.get("total_tokens"):
                            self._last_actual_tokens = usage["total_tokens"]
                        elif usage.get("input_tokens"):
                            self._last_actual_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                        _last_response_id = event.raw.get("id")
                        _last_response_usage = event.raw.get("usage", {})
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
                err_str = str(e)
                # Reactive compact on prompt-too-long (413)
                if "413" in err_str or "prompt_too_long" in err_str or "too long" in err_str.lower():
                    self._reactive_compact()
                    yield CompactEvent(
                        pre_tokens=self.est_tokens(),
                        post_tokens=self.est_tokens(),
                        trigger="reactive (413)",
                    )
                    # Retry after compact
                    try:
                        text_parts = []
                        tool_use_blocks = []
                        async for event in self.provider.call_stream(
                            messages=self.messages,
                            tools=tools_schema,
                            system=system_prompt,
                        ):
                            if isinstance(event, TextDeltaEvent):
                                if not event.reasoning:
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
                                usage = event.raw.get("usage", {})
                                if usage.get("total_tokens"):
                                    self._last_actual_tokens = usage["total_tokens"]
                                elif usage.get("input_tokens"):
                                    self._last_actual_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                                _last_response_id = event.raw.get("id")
                                _last_response_usage = event.raw.get("usage", {})
                                yield event
                            elif isinstance(event, ErrorEvent):
                                self.messages.append(Message(
                                    role="assistant",
                                    content=f"Error after compaction: {event.message}",
                                ))
                                yield event
                                yield DoneEvent(final_text=f"Error after compaction: {event.message}")
                                return
                        # Retry succeeded — process response
                        assistant_text = "".join(text_parts)
                        assistant_msg = Message(
                            role="assistant",
                            content=assistant_text,
                            tool_use_blocks=tool_use_blocks,
                            id=_last_response_id,
                            usage=_last_response_usage,
                        )
                        self.messages.append(assistant_msg)
                        if not tool_use_blocks:
                            yield DoneEvent(final_text=assistant_text or "(no response)")
                            return
                        context = ToolContext(cwd=self.cwd, messages=list(self.messages))
                        for block in tool_use_blocks:
                            tool = self.registry.get(block.tool_name)
                            if tool is None:
                                result_text = json.dumps({"error": f"Unknown tool: {block.tool_name}"})
                                is_error = True
                            else:
                                import time
                                t0 = time.time()
                                try:
                                    result_text = await tool.call(block.input, context)
                                    is_error = False
                                    result_text = process_tool_result_block(
                                        result_text, tool.name, block.tool_use_id,
                                        getattr(tool, 'max_result_chars', None), self.cwd)
                                except Exception as te:
                                    result_text = f"Tool error: {te}"
                                    is_error = True
                                duration_ms = (time.time() - t0) * 1000
                            yield ToolDoneEvent(
                                tool_name=block.tool_name,
                                result=result_text,
                                is_error=is_error,
                                duration_ms=duration_ms,
                                tool_use_id=block.tool_use_id,
                            )
                            self.messages.append(Message(
                                role="user",
                                content=result_text,
                                tool_use_id=block.tool_use_id,
                            ))
                        continue  # back to while loop top
                    except Exception as e2:
                        error_msg_text = f"Error calling LLM after compaction: {e2}"
                        self.messages.append(Message(
                            role="assistant",
                            content=error_msg_text,
                        ))
                        yield ErrorEvent(message=error_msg_text)
                        yield DoneEvent(final_text=error_msg_text)
                        return
                else:
                    error_msg_text = f"Error calling LLM: {e}"
                    self.messages.append(Message(
                        role="assistant",
                        content=error_msg_text,
                    ))
                    yield ErrorEvent(message=error_msg_text)
                    yield DoneEvent(final_text=error_msg_text)
                    return

            assistant_text = "".join(text_parts)
            assistant_msg = Message(
                role="assistant",
                content=assistant_text,
                tool_use_blocks=tool_use_blocks,
                id=_last_response_id,
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
                    import time
                    t0 = time.time()
                    try:
                        result_text = await tool.call(block.input, context)
                        is_error = False
                        result_text = process_tool_result_block(
                            result_text, tool.name, block.tool_use_id,
                            getattr(tool, 'max_result_chars', None), self.cwd)
                    except Exception as e:
                        result_text = f"Tool error: {e}"
                        is_error = True
                    duration_ms = (time.time() - t0) * 1000

                yield ToolDoneEvent(
                    tool_name=block.tool_name,
                    result=result_text,
                    is_error=is_error,
                    duration_ms=duration_ms,
                    tool_use_id=block.tool_use_id,
                )

                self.messages.append(Message(
                    role="user",
                    content=result_text,
                    tool_use_id=block.tool_use_id,
                ))

        yield DoneEvent(final_text="Agent: max turns reached without completing the task.")
