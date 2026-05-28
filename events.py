"""Streaming event types shared by Agent, Providers, and UI."""

from dataclasses import dataclass
from typing import Any


@dataclass
class ThinkingEvent:
    """Agent 开始思考（发起 LLM 请求前）"""


@dataclass
class TextDeltaEvent:
    """LLM 返回的一个文本 token"""
    token: str
    reasoning: bool = False  # True for model internal thinking (GLM reasoning_content)


@dataclass
class ToolUseEvent:
    """LLM 请求调用工具"""
    tool_name: str
    input: dict[str, Any]
    tool_use_id: str = ""


@dataclass
class ToolDoneEvent:
    """工具执行完毕"""
    tool_name: str
    result: str
    is_error: bool = False
    duration_ms: float = 0
    tool_use_id: str = ""


@dataclass
class ResponseDoneEvent:
    """LLM 响应完成，含原始 API 返回数据"""
    raw: dict[str, Any]


@dataclass
class DoneEvent:
    """整个 run_stream() 完成"""
    final_text: str


@dataclass
class ErrorEvent:
    """发生错误"""
    message: str


@dataclass
class CompactCallEvent:
    """准备发起压缩请求"""
    old_msg_count: int
    pre_tokens: int


@dataclass
class CompactEvent:
    """上下文压缩完成"""
    pre_tokens: int
    post_tokens: int
    trigger: str = ""
    summary: str = ""


@dataclass
class SnipEvent:
    """Snip 截断 —— 删除最老的 API-round 组以保持在窗口上限内"""
    groups_removed: int
    messages_removed: int
    tokens_before: int
    tokens_after: int
