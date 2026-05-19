# My Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a multi-provider Python agent framework extracting Claude Code's core architecture (agent loop, tool system, provider abstraction).

**Architecture:** Three-layer design: Agent (session + while loop) → Provider (API abstraction, streaming + tool schema serialization) → Tools (ABC + registry + 6 builtins). Termination by model-driven `needsFollowUp` only.

**Tech Stack:** Python 3.11+, anthropic SDK, openai SDK, pydantic, asyncio

---

### Task 1: Create `__init__.py` files for packages

**Files:**
- Create: `tools/__init__.py`
- Create: `providers/__init__.py`

- [ ] **Step 1: Create tools/__init__.py**

```python
"""Tools package for the agent framework."""
```

- [ ] **Step 2: Create providers/__init__.py**

```python
"""Provider package for the agent framework."""
```

---

### Task 2: Implement `tools/base.py` — Tool abstract base class

**Files:**
- Create: `tools/base.py`

- [ ] **Step 1: Write tools/base.py**

```python
"""Tool abstract base class — mirrors Claude Code's Tool interface (Tool.ts)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ToolContext:
    """Context passed to tools during execution (mirrors ToolUseContext from Tool.ts)."""
    cwd: Path
    messages: list = field(default_factory=list)


class Tool(ABC):
    """
    Abstract base class for all tools.
    Mirrors the Tool type from Tool.ts:
    - name, description, parameters → schema for the LLM
    - call() → execution logic
    """

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)

    @abstractmethod
    async def call(self, input: dict[str, Any], context: ToolContext) -> str:
        """Execute the tool with given input and context. Returns result string."""
        ...

    def is_enabled(self) -> bool:
        return True

    def is_read_only(self) -> bool:
        return False

    def get_schema(self) -> dict[str, Any]:
        """Serialize to API-compatible JSON Schema (mirrors toolToAPISchema)."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
```

---

### Task 3: Implement `tools/registry.py` — ToolRegistry

**Files:**
- Create: `tools/registry.py`

- [ ] **Step 1: Write tools/registry.py**

```python
"""Tool registry — mirrors Claude Code's tools.ts registry."""

from .base import Tool


class ToolRegistry:
    """Manages tool registration, lookup, and schema generation."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def register_all(self, tools: list[Tool]) -> None:
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_enabled(self) -> list[Tool]:
        return [t for t in self._tools.values() if t.is_enabled()]

    def get_schemas(self) -> list[dict]:
        """Get API-compatible schemas for all enabled tools (管道二: API tools[])."""
        return [t.get_schema() for t in self.list_enabled()]

    def get_tool_names(self) -> list[str]:
        return [t.name for t in self.list_enabled()]
```

---

### Task 4: Implement built-in tools

**Files:**
- Create: `tools/bash.py`
- Create: `tools/file_read.py`
- Create: `tools/file_edit.py`
- Create: `tools/file_write.py`
- Create: `tools/glob.py`
- Create: `tools/grep.py`

- [ ] **Step 1: Write tools/bash.py**

```python
"""Bash tool — execute shell commands (mirrors BashTool/BashTool.tsx)."""

import asyncio
import subprocess
from typing import Any

from .base import Tool, ToolContext


class BashTool(Tool):
    name = "Bash"
    description = "Execute a shell command in the project's working directory."
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute"
            }
        },
        "required": ["command"]
    }

    async def call(self, input: dict[str, Any], context: ToolContext) -> str:
        command = input.get("command", "")
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(context.cwd),
            )
            stdout, stderr = await process.communicate()
            result = stdout.decode("utf-8", errors="replace")
            if stderr:
                result += "\n[stderr]\n" + stderr.decode("utf-8", errors="replace")
            if process.returncode != 0:
                result += f"\n[exit code: {process.returncode}]"
            return result.strip() or "(no output)"
        except Exception as e:
            return f"Error executing command: {e}"
```

- [ ] **Step 2: Write tools/file_read.py**

```python
"""FileRead tool — read file contents (mirrors FileReadTool/FileReadTool.ts)."""

from pathlib import Path
from typing import Any

from .base import Tool, ToolContext


class FileReadTool(Tool):
    name = "FileRead"
    description = "Read the contents of a file at the given path."
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the file to read"
            }
        },
        "required": ["file_path"]
    }

    def is_read_only(self) -> bool:
        return True

    async def call(self, input: dict[str, Any], context: ToolContext) -> str:
        path = Path(input["file_path"])
        if not path.is_absolute():
            path = context.cwd / path
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            return content
        except FileNotFoundError:
            return f"Error: File not found: {path}"
        except PermissionError:
            return f"Error: Permission denied: {path}"
        except Exception as e:
            return f"Error reading file: {e}"
```

- [ ] **Step 3: Write tools/file_edit.py**

```python
"""FileEdit tool — exact string replacement (mirrors FileEditTool/FileEditTool.ts)."""

from pathlib import Path
from typing import Any

from .base import Tool, ToolContext


class FileEditTool(Tool):
    name = "FileEdit"
    description = (
        "Make exact string replacements in a file. "
        "Provide the exact text to find (old_string) and its replacement (new_string). "
        "old_string must match exactly including whitespace."
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the file to edit"
            },
            "old_string": {
                "type": "string",
                "description": "The exact text to find and replace"
            },
            "new_string": {
                "type": "string",
                "description": "The replacement text"
            },
        },
        "required": ["file_path", "old_string", "new_string"]
    }

    async def call(self, input: dict[str, Any], context: ToolContext) -> str:
        path = Path(input["file_path"])
        if not path.is_absolute():
            path = context.cwd / path
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return f"Error: File not found: {path}"

        old = input["old_string"]
        new = input["new_string"]

        count = content.count(old)
        if count == 0:
            return f"Error: old_string not found in {path}"
        if count > 1:
            return (
                f"Error: old_string appears {count} times in {path}. "
                "Provide a larger string with more surrounding context to make it unique."
            )

        content = content.replace(old, new)
        path.write_text(content, encoding="utf-8")
        return f"Successfully edited {path}: 1 replacement made."
```

- [ ] **Step 4: Write tools/file_write.py**

```python
"""FileWrite tool — create or overwrite files (mirrors FileWriteTool/FileWriteTool.ts)."""

from pathlib import Path
from typing import Any

from .base import Tool, ToolContext


class FileWriteTool(Tool):
    name = "FileWrite"
    description = (
        "Create a new file or completely overwrite an existing file "
        "with the given content."
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the file to write"
            },
            "content": {
                "type": "string",
                "description": "The content to write to the file"
            },
        },
        "required": ["file_path", "content"]
    }

    async def call(self, input: dict[str, Any], context: ToolContext) -> str:
        path = Path(input["file_path"])
        if not path.is_absolute():
            path = context.cwd / path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(input["content"], encoding="utf-8")
            return f"Successfully wrote to {path} ({len(input['content'])} characters)."
        except Exception as e:
            return f"Error writing file: {e}"
```

- [ ] **Step 5: Write tools/glob.py**

```python
"""Glob tool — file pattern matching (mirrors GlobTool/GlobTool.ts)."""

from pathlib import Path
from typing import Any

from .base import Tool, ToolContext


class GlobTool(Tool):
    name = "Glob"
    description = "Find files matching a glob pattern (e.g., '**/*.py', 'src/**/*.ts')."
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "The glob pattern to match file paths"
            },
        },
        "required": ["pattern"]
    }

    def is_read_only(self) -> bool:
        return True

    async def call(self, input: dict[str, Any], context: ToolContext) -> str:
        pattern = input["pattern"]
        try:
            results = sorted(str(p) for p in context.cwd.glob(pattern))
            if not results:
                return f"No files matched pattern: {pattern}"
            return "\n".join(results[:200])
        except Exception as e:
            return f"Error in glob search: {e}"
```

- [ ] **Step 6: Write tools/grep.py**

```python
"""Grep tool — regex content search (mirrors GrepTool/GrepTool.ts)."""

import re
from pathlib import Path
from typing import Any

from .base import Tool, ToolContext


class GrepTool(Tool):
    name = "Grep"
    description = (
        "Search file contents using a regex pattern. "
        "Returns file paths and matching lines."
    )
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "The regex pattern to search for"
            },
            "path": {
                "type": "string",
                "description": "Directory to search in (default: cwd)"
            },
        },
        "required": ["pattern"]
    }

    def is_read_only(self) -> bool:
        return True

    async def call(self, input: dict[str, Any], context: ToolContext) -> str:
        pattern = input["pattern"]
        search_dir = Path(input.get("path", context.cwd))
        try:
            compiled = re.compile(pattern)
        except re.error as e:
            return f"Error: Invalid regex pattern: {e}"

        results: list[str] = []
        seen = 0
        try:
            for file_path in sorted(search_dir.rglob("*")):
                if file_path.is_dir() or ".git" in file_path.parts:
                    continue
                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                for line_no, line in enumerate(content.splitlines(), 1):
                    if compiled.search(line):
                        results.append(f"{file_path}:{line_no}: {line.strip()}")
                        seen += 1
                        if seen >= 200:
                            break
                if seen >= 200:
                    break
            if not results:
                return f"No matches found for pattern: {pattern}"
            return "\n".join(results)
        except Exception as e:
            return f"Error in grep search: {e}"
```

---

### Task 5: Implement `providers/base.py` — BaseProvider ABC

**Files:**
- Create: `providers/base.py`

- [ ] **Step 1: Write providers/base.py**

```python
"""Base provider abstraction — mirrors services/api/claude.ts interface."""

from abc import ABC, abstractmethod

from types import Message, ToolUseBlock


class BaseProvider(ABC):
    """Abstract base for LLM providers."""

    @abstractmethod
    async def call(
        self,
        messages: list[Message],
        tools: list[dict],
        system: str,
    ) -> tuple[Message, list[ToolUseBlock]]:
        """
        Stream call to LLM, returning the assistant message and tool_use blocks.

        Returns:
            (assistant_message, tool_use_blocks)
            - assistant_message: Message with role="assistant", content=text
            - tool_use_blocks: list of ToolUseBlock extracted from the response
        """
        ...
```

---

### Task 6: Implement `providers/anthropic.py` — AnthropicProvider

**Files:**
- Create: `providers/anthropic.py`

- [ ] **Step 1: Write providers/anthropic.py**

```python
"""Anthropic provider — mirrors services/api/claude.ts callModel."""

import os
from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic

from types import Message, ToolUseBlock
from .base import BaseProvider


class AnthropicProvider(BaseProvider):
    """Uses Anthropic SDK for native tool_use blocks."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-6-20250514",
        api_key: str | None = None,
        max_tokens: int = 16000,
    ):
        self.model = model
        self.max_tokens = max_tokens
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        self.client = AsyncAnthropic(api_key=key)

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
                api_messages.append(_assistant_to_api(msg))

        # Build API-format tools (管道二)
        api_tools = [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["parameters"],
            }
            for t in tools
        ] if tools else None

        # Stream the API call
        text_parts: list[str] = []
        tool_use_blocks: list[ToolUseBlock] = []
        tool_use_buffer: dict[str, dict] = {}
        current_block: dict | None = None

        async with self.client.beta.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=api_messages,
            tools=api_tools,
        ) as stream:
            async for event in stream:
                if event.type == "content_block_start":
                    current_block = event.content_block
                    if current_block and current_block.type == "tool_use":
                        block_data = {
                            "id": current_block.id,
                            "name": current_block.name,
                            "input": "",
                        }
                        tool_use_buffer[current_block.index or 0] = block_data

                elif event.type == "content_block_delta":
                    delta = event.delta
                    if hasattr(delta, "text") and delta.text:
                        text_parts.append(delta.text)
                    elif hasattr(delta, "partial_json") and delta.partial_json:
                        idx = event.index
                        if idx in tool_use_buffer:
                            tool_use_buffer[idx]["input"] += delta.partial_json

                elif event.type == "content_block_stop":
                    current_block = None

        # Parse tool_use blocks from the buffer
        import json
        for block_data in tool_use_buffer.values():
            try:
                parsed = json.loads(block_data["input"]) if block_data["input"] else {}
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


def _assistant_to_api(msg: Message) -> dict:
    """Convert an assistant Message to Anthropic API format."""
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
```

---

### Task 7: Implement `providers/openai_compat.py` — OpenAI/GLM/DeepSeek

**Files:**
- Create: `providers/openai_compat.py`

- [ ] **Step 1: Write providers/openai_compat.py**

```python
"""OpenAI-compatible provider — supports OpenAI, GLM, DeepSeek APIs."""

import json
import os

from openai import AsyncOpenAI

from types import Message, ToolUseBlock
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
    Tool calling via function calling protocol.
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
        # Convert our Message format to OpenAI API format
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
        ] if tools else None

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
    """Convert an assistant Message to OpenAI API format."""
    result: dict = {"role": "assistant", "content": msg.content or None}
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
```

---

### Task 8: Implement `prompts.py` — System Prompt Assembly

**Files:**
- Create: `prompts.py`

- [ ] **Step 1: Write prompts.py**

```python
"""System prompt assembly — mirrors constants/prompts.ts getSystemPrompt().

Two pipes to the LLM:
管道一: System prompt text — tells the model what tools exist and how to use them
管道二: API tools[] schemas — structured definitions enabling actual tool calls
"""

from datetime import datetime


def build_system_prompt(tools: list[str], cwd: str) -> str:
    """
    Build the full system prompt string.
    Static section (cacheable) + dynamic section (date, cwd).
    """
    sections = [
        _get_role_section(),
        _get_doing_tasks_section(),
        _get_using_your_tools_section(tools),
        _get_tone_section(),
        _get_dynamic_section(cwd),
    ]
    return "\n\n".join(s for s in sections if s)


def _get_role_section() -> str:
    return (
        "You are an interactive coding agent that helps users with "
        "software engineering tasks. You work in the user's terminal, "
        "reading and editing files in their project directory."
    )


def _get_doing_tasks_section() -> str:
    return (
        "# Doing tasks\n\n"
        "The user will ask you to perform software engineering tasks. "
        "These may include fixing bugs, adding new functionality, "
        "refactoring code, explaining code, and more.\n\n"
        "- Prefer editing existing files to creating new ones.\n"
        "- Be careful not to introduce security vulnerabilities.\n"
        "- Don't add features, refactor, or introduce abstractions "
        "beyond what the task requires.\n"
        "- Default to writing no comments."
    )


def _get_using_your_tools_section(tool_names: list[str]) -> str:
    """Generate tool usage guidance (mirrors getUsingYourToolsSection in prompts.ts)."""
    lines = [
        "# Using your tools",
        "",
        "You have access to a set of tools for file operations and system commands.",
        "Prefer dedicated tools over Bash when available:",
        "",
    ]

    tool_guidance = {
        "FileRead": "To read files use FileRead instead of cat, head, or tail",
        "FileEdit": "To edit files use FileEdit instead of sed or awk",
        "FileWrite": "To create files use FileWrite instead of cat with heredoc or echo redirection",
        "Glob": "To search for files by pattern use Glob instead of find or ls",
        "Grep": "To search file contents use Grep instead of grep or rg",
        "Bash": "Reserve Bash exclusively for system commands and terminal operations that require shell execution. If there is a relevant dedicated tool, default to using it and only fall back to Bash when absolutely necessary.",
    }

    for name in tool_names:
        if name in tool_guidance:
            lines.append(f"- {tool_guidance[name]}")

    lines.extend([
        "",
        "You can call multiple tools in a single response. When there are no "
        "dependencies between them, make all independent tool calls in parallel. "
        "If some tool calls depend on previous calls, run them sequentially instead.",
    ])

    return "\n".join(lines)


def _get_tone_section() -> str:
    return (
        "# Tone and style\n\n"
        "Keep responses short and direct. "
        "Default to writing no comments in code. "
        "Only explain when the WHY is non-obvious."
    )


def _get_dynamic_section(cwd: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f"# Environment\n\n"
        f"Current date: {now}\n"
        f"Working directory: {cwd}\n"
    )
```

---

### Task 9: Implement `agent.py` — Core Agent Loop

**Files:**
- Create: `agent.py`

- [ ] **Step 1: Write agent.py**

```python
"""Agent core loop — mirrors query.ts while(true) with needsFollowUp termination."""

import json
from pathlib import Path
from types import Message, ToolResult
from tools.base import ToolContext
from tools.registry import ToolRegistry
from providers.base import BaseProvider
from prompts import build_system_prompt


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
    ):
        self.provider = provider
        self.registry = registry
        self.cwd = Path(cwd) if cwd else Path.cwd()
        self.max_turns = max_turns
        self.max_messages = max_messages
        self.messages: list[Message] = []

    async def run(self, user_message: str) -> str:
        """Process one user message. May involve multiple LLM↔tool rounds."""
        self.messages.append(Message(role="user", content=user_message))

        turn_count = 0
        while turn_count < self.max_turns:
            turn_count += 1

            # Apply simple message cap — keep last N messages (naive snip)
            if len(self.messages) > self.max_messages:
                self.messages = self.messages[-self.max_messages:]

            # 1. Call LLM — get assistant response + tool_use blocks
            tools_schema = self.registry.get_schemas()
            system_prompt = build_system_prompt(
                self.registry.get_tool_names(),
                str(self.cwd),
            )

            try:
                assistant_msg, tool_use_blocks = await self.provider.call(
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

            # 2. Termination check — mirrors query.ts:1062
            if not tool_use_blocks:
                return assistant_msg.content or "(no response)"

            # 3. Execute tools — mirrors query.ts:1366
            context = ToolContext(cwd=self.cwd, messages=list(self.messages))
            for block in tool_use_blocks:
                tool = self.registry.get(block.tool_name)
                if tool is None:
                    result_text = json.dumps({
                        "error": f"Unknown tool: {block.tool_name}"
                    })
                else:
                    try:
                        result_text = await tool.call(block.input, context)
                    except Exception as e:
                        result_text = f"Tool error: {e}"

                self.messages.append(Message(
                    role="user",
                    content=result_text,
                    tool_use_id=block.tool_use_id,
                ))

        return "Agent: max turns reached without completing the task."
```

---

### Task 10: Implement `config.py` and `main.py`

**Files:**
- Create: `config.py`
- Create: `main.py`

- [ ] **Step 1: Write config.py**

```python
"""Configuration management for the agent framework."""

import os
from dataclasses import dataclass, field


@dataclass
class AgentConfig:
    """Agent configuration — provider, model, tools, limits."""

    provider: str = "anthropic"  # anthropic | openai | glm | deepseek
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    cwd: str | None = None
    max_turns: int = 50
    max_messages: int = 200
    verbose: bool = False

    @classmethod
    def from_env(cls, provider: str | None = None) -> "AgentConfig":
        """Create config from environment variables."""
        provider_name = provider or os.environ.get("AGENT_PROVIDER", "anthropic")
        return cls(
            provider=provider_name,
            model=os.environ.get("AGENT_MODEL"),
            api_key=os.environ.get("AGENT_API_KEY"),
            base_url=os.environ.get("AGENT_BASE_URL"),
            cwd=os.environ.get("AGENT_CWD"),
            max_turns=int(os.environ.get("AGENT_MAX_TURNS", "50")),
            max_messages=int(os.environ.get("AGENT_MAX_MESSAGES", "200")),
            verbose=os.environ.get("AGENT_VERBOSE", "").lower() in ("1", "true", "yes"),
        )
```

- [ ] **Step 2: Write main.py**

```python
"""Entry point for the agent CLI."""

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
    """Build the tool registry with all built-in coding tools."""
    registry = ToolRegistry()
    registry.register_all([
        BashTool(),
        FileReadTool(),
        FileEditTool(),
        FileWriteTool(),
        GlobTool(),
        GrepTool(),
    ])
    return registry


def build_provider(config: AgentConfig):
    """Build the provider based on configuration."""
    provider_name = config.provider.lower()
    if provider_name == "anthropic":
        return AnthropicProvider(
            model=config.model or "claude-sonnet-4-6-20250514",
            api_key=config.api_key,
        )
    else:
        return OpenAICompatProvider(
            provider=provider_name,
            model=config.model,
            api_key=config.api_key,
            base_url=config.base_url,
        )


async def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <your message>")
        print("  e.g. python main.py 'List files in the current directory'")
        print()
        print("Environment variables:")
        print("  ANTHROPIC_API_KEY  — for Anthropic provider")
        print("  OPENAI_API_KEY     — for OpenAI provider")
        print("  GLM_API_KEY        — for GLM provider")
        print("  DEEPSEEK_API_KEY   — for DeepSeek provider")
        print("  AGENT_PROVIDER     — provider name (anthropic|openai|glm|deepseek)")
        print("  AGENT_MODEL        — model name override")
        sys.exit(1)

    config = AgentConfig.from_env()
    user_message = " ".join(sys.argv[1:])

    registry = build_registry()
    provider = build_provider(config)
    agent = Agent(
        provider=provider,
        registry=registry,
        cwd=config.cwd,
        max_turns=config.max_turns,
        max_messages=config.max_messages,
    )

    if config.verbose:
        print(f"[Agent] Provider: {config.provider}, Model: {provider.model}")
        print(f"[Agent] Tools: {registry.get_tool_names()}")
        print(f"[Agent] CWD: {agent.cwd}")
        print()

    print("Working...", flush=True)
    try:
        result = await agent.run(user_message)
        print()
        print(result)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
```

---

### Task 11: Verify end-to-end with Anthropic

**Files:**
- Test: `test_run.py` (one-shot test script)

- [ ] **Step 1: Write test_run.py**

```python
"""Quick end-to-end test script."""

import asyncio
import os
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
from agent import Agent


async def test():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("SKIP: ANTHROPIC_API_KEY not set")
        return

    registry = ToolRegistry()
    registry.register_all([
        BashTool(), FileReadTool(), FileEditTool(),
        FileWriteTool(), GlobTool(), GrepTool(),
    ])

    provider = AnthropicProvider(model="claude-sonnet-4-6-20250514")
    agent = Agent(provider=provider, registry=registry)
    agent.cwd = os.getcwd()

    print("Test: List current directory")
    result = await agent.run("ls the current directory and tell me what you see")

    print(f"Result length: {len(result)} chars")
    print(f"Turn count: {len(agent.messages)} messages")
    print(f"Tools used: {[m.tool_use_id for m in agent.messages if m.has_tool_uses]}")
    print("PASS" if len(result) > 0 else "FAIL: empty result")


if __name__ == "__main__":
    asyncio.run(test())
```

- [ ] **Step 2: Run test**

```bash
cd D:\space\labspace\my_agent
pip install -r requirements.txt
python test_run.py
```

Expected: Agent calls `ls`, gets result, returns text summary.

---
