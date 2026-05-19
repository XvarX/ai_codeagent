"""OpenAI-compatible provider — supports OpenAI, GLM, DeepSeek APIs."""

import json
import os
from openai import AsyncOpenAI
from core_types import Message, ToolUseBlock
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
    ) -> tuple[Message, list[ToolUseBlock]]:
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

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=api_messages,
            tools=openai_tools,
            max_tokens=self.max_tokens,
        )

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
        return assistant_msg, tool_use_blocks


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
