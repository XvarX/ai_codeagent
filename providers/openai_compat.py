"""OpenAI-compatible provider — supports OpenAI, GLM, DeepSeek APIs."""

import json
import os
from openai import AsyncOpenAI
from core_types import Message, ToolUseBlock
from events import TextDeltaEvent, ToolUseEvent, ResponseDoneEvent, ErrorEvent
from .base import BaseProvider


PROVIDER_CONFIGS = {
    "openai": {
        "env_key": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
    },
    "glm": {
        "env_key": "GLM_API_KEY",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-4.7",
    },
    "deepseek": {
        "env_key": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
    },
}


class OpenAICompatProvider(BaseProvider):
    """
    Uses OpenAI SDK for OpenAI / GLM / DeepSeek.
    Converts between our Message format and OpenAI's tool calling protocol.
    """

    def __init__(
        self,
        provider: str = "openai",
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 16000,
    ):
        config = PROVIDER_CONFIGS.get(provider, PROVIDER_CONFIGS["openai"])
        self.provider_name = provider
        self.model = model or config["default_model"]
        self.max_tokens = max_tokens

        key = api_key or os.environ.get(config["env_key"], "")
        if not key:
            raise ValueError(f"{config['env_key']} not set for provider '{provider}'")

        url = base_url or os.environ.get(f"{provider.upper()}_BASE_URL", "") or config["base_url"]
        self.client = AsyncOpenAI(api_key=key, base_url=url)

    async def call(
        self,
        messages: list[Message],
        tools: list[dict],
        system: str,
    ) -> tuple[Message, list[ToolUseBlock], dict]:
        # Build OpenAI-format messages
        api_messages: list[dict] = [{"role": "system", "content": system}]

        for msg in messages:
            if msg.is_tool_result:
                api_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_use_id,
                    "content": msg.content,
                })
            elif msg.role == "user":
                api_messages.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                api_messages.append(_assistant_to_openai(msg))

        # Build OpenAI-format tools
        openai_tools = None
        if tools:
            openai_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["parameters"],
                    },
                }
                for t in tools
            ]

        request_payload = {
            "model": self.model,
            "messages": api_messages,
            "tools": openai_tools,
            "max_tokens": self.max_tokens,
        }

        response = await self.client.chat.completions.create(**request_payload)

        choice = response.choices[0]
        message = choice.message

        text = message.content or ""
        tool_use_blocks: list[ToolUseBlock] = []

        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    parsed_input = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    parsed_input = {}
                tool_use_blocks.append(ToolUseBlock(
                    tool_use_id=tc.id,
                    tool_name=tc.function.name,
                    input=parsed_input,
                ))

        assistant_msg = Message(
            role="assistant",
            content=text,
            tool_use_blocks=tool_use_blocks,
        )
        raw = response.model_dump()
        raw["_provider"] = self.provider_name
        raw["_request"] = request_payload
        return assistant_msg, tool_use_blocks, raw

    async def call_stream(self, messages, tools, system):
        """OpenAI/GLM/DeepSeek 流式调用，逐 token yield."""
        from core_types import ToolUseBlock

        # Build API messages (same as call())
        api_messages: list[dict] = [{"role": "system", "content": system}]
        for msg in messages:
            if msg.is_tool_result:
                api_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_use_id,
                    "content": msg.content,
                })
            elif msg.role == "user":
                api_messages.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                api_messages.append(_assistant_to_openai(msg))

        openai_tools = None
        if tools:
            openai_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["parameters"],
                    },
                }
                for t in tools
            ]

        request_payload = {
            "model": self.model,
            "messages": api_messages,
            "tools": openai_tools,
            "max_tokens": self.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        try:
            stream = await self.client.chat.completions.create(**request_payload)

            text_parts: list[str] = []
            tool_calls_buffer: dict[int, dict] = {}
            final_usage: dict = {}

            async for chunk in stream:
                if not chunk.choices:
                    if hasattr(chunk, "usage") and chunk.usage:
                        final_usage = chunk.usage.model_dump() if hasattr(chunk.usage, "model_dump") else {}
                    continue

                delta = chunk.choices[0].delta

                if delta.content:
                    text_parts.append(delta.content)
                    yield TextDeltaEvent(token=delta.content)

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_buffer:
                            tool_calls_buffer[idx] = {
                                "id": tc.id or "",
                                "name": tc.function.name or "",
                                "arguments": "",
                            }
                        if tc.id:
                            tool_calls_buffer[idx]["id"] = tc.id
                        if tc.function.name:
                            tool_calls_buffer[idx]["name"] = tc.function.name
                        if tc.function.arguments:
                            tool_calls_buffer[idx]["arguments"] += tc.function.arguments

                if hasattr(chunk, "usage") and chunk.usage:
                    final_usage = chunk.usage.model_dump() if hasattr(chunk.usage, "model_dump") else {}

            # Build raw response
            raw = {
                "_provider": self.provider_name,
                "_request": request_payload,
                "model": self.model,
                "usage": final_usage,
            }

            # Parse tool calls from buffer
            tool_use_blocks: list[ToolUseBlock] = []
            for tc_data in tool_calls_buffer.values():
                try:
                    parsed = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                except json.JSONDecodeError:
                    parsed = {}
                block = ToolUseBlock(
                    tool_use_id=tc_data["id"],
                    tool_name=tc_data["name"],
                    input=parsed,
                )
                tool_use_blocks.append(block)
                yield ToolUseEvent(
                    tool_name=tc_data["name"],
                    input=parsed,
                    tool_use_id=tc_data["id"],
                )

            raw["_tool_use_blocks"] = [
                {"tool_name": t.tool_name, "tool_use_id": t.tool_use_id, "input": t.input}
                for t in tool_use_blocks
            ]
            yield ResponseDoneEvent(raw=raw)

        except Exception as e:
            yield ErrorEvent(message=f"Provider error: {e}")


def _assistant_to_openai(msg: Message) -> dict:
    """Convert our assistant Message to OpenAI API format."""
    result: dict = {"role": "assistant"}
    if msg.content:
        result["content"] = msg.content
    else:
        result["content"] = None
    if msg.tool_use_blocks:
        result["tool_calls"] = [
            {
                "id": block.tool_use_id,
                "type": "function",
                "function": {
                    "name": block.tool_name,
                    "arguments": json.dumps(block.input, ensure_ascii=False),
                },
            }
            for block in msg.tool_use_blocks
        ]
    return result
