"""Anthropic provider — mirrors services/api/claude.ts callModel with native tool_use."""

import json
import os
from anthropic import AsyncAnthropic
from core_types import Message, ToolUseBlock
from .base import BaseProvider


class AnthropicProvider(BaseProvider):
    """Uses Anthropic SDK with native tool_use content blocks."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-6-20250514",
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 16000,
    ):
        self.model = model
        self.max_tokens = max_tokens
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        kwargs = {"api_key": key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = AsyncAnthropic(**kwargs)

    async def call(
        self,
        messages: list[Message],
        tools: list[dict],
        system: str,
    ) -> tuple[Message, list[ToolUseBlock]]:
        # Convert our Message format to Anthropic API format
        api_messages: list[dict] = []
        for msg in messages:
            if msg.is_tool_result:
                api_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_use_id,
                        "content": msg.content,
                    }],
                })
            elif msg.role == "user":
                api_messages.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                api_messages.append(_assistant_to_anthropic(msg))

        # Build API-format tools (管道二: structured schema)
        api_tools = None
        if tools:
            api_tools = [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "input_schema": t["parameters"],
                }
                for t in tools
            ]

        text_parts: list[str] = []
        tool_use_blocks: list[ToolUseBlock] = []
        tool_use_buffer: dict[int, dict] = {}

        async with self.client.beta.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=api_messages,
            tools=api_tools,
        ) as stream:
            async for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        idx = event.index
                        tool_use_buffer[idx] = {
                            "id": block.id,
                            "name": block.name,
                            "input_json": "",
                        }

                elif event.type == "content_block_delta":
                    delta = event.delta
                    if hasattr(delta, "text") and delta.text:
                        text_parts.append(delta.text)
                    elif hasattr(delta, "partial_json") and delta.partial_json:
                        idx = event.index
                        if idx in tool_use_buffer:
                            tool_use_buffer[idx]["input_json"] += delta.partial_json

        # Parse accumulated tool_use input JSON
        for block_data in tool_use_buffer.values():
            try:
                parsed = json.loads(block_data["input_json"]) if block_data["input_json"] else {}
            except json.JSONDecodeError:
                parsed = {}
            tool_use_blocks.append(ToolUseBlock(
                tool_use_id=block_data["id"],
                tool_name=block_data["name"],
                input=parsed,
            ))

        assistant_msg = Message(
            role="assistant",
            content="\n".join(text_parts) if text_parts else "",
            tool_use_blocks=tool_use_blocks,
        )
        return assistant_msg, tool_use_blocks


def _assistant_to_anthropic(msg: Message) -> dict:
    """Convert our assistant Message to Anthropic API message format."""
    content: list[dict] = []
    if msg.content:
        content.append({"type": "text", "text": msg.content})
    for block in msg.tool_use_blocks:
        content.append({
            "type": "tool_use",
            "id": block.tool_use_id,
            "name": block.tool_name,
            "input": block.input,
        })
    return {"role": "assistant", "content": content}
