"""QThread worker that runs Agent.run_stream() and emits Qt signals."""

import asyncio
import json

from PySide6.QtCore import QThread, Signal

from events import (
    ThinkingEvent, TextDeltaEvent, ToolUseEvent, ToolDoneEvent,
    ResponseDoneEvent, DoneEvent, ErrorEvent,
)


class AgentWorker(QThread):
    """Runs Agent.run_stream() in a worker thread, emits signals per event."""

    thinking = Signal()
    text_delta = Signal(str)
    tool_use = Signal(str, str, str)        # name, input_json, tool_use_id
    tool_done = Signal(str, str, bool)      # name, result, is_error
    response_done = Signal(str)             # raw JSON string
    done = Signal(str)
    error = Signal(str)

    def __init__(self, agent, user_message: str, parent=None):
        super().__init__(parent)
        self.agent = agent
        self.user_message = user_message
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        asyncio.run(self._run())

    async def _run(self):
        try:
            async for event in self.agent.run_stream(self.user_message):
                if self._cancel:
                    break

                if isinstance(event, ThinkingEvent):
                    self.thinking.emit()
                elif isinstance(event, TextDeltaEvent):
                    self.text_delta.emit(event.token)
                elif isinstance(event, ToolUseEvent):
                    self.tool_use.emit(
                        event.tool_name,
                        json.dumps(event.input, ensure_ascii=False),
                        event.tool_use_id,
                    )
                elif isinstance(event, ToolDoneEvent):
                    self.tool_done.emit(event.tool_name, event.result, event.is_error)
                elif isinstance(event, ResponseDoneEvent):
                    self.response_done.emit(
                        json.dumps(event.raw, ensure_ascii=False)
                    )
                elif isinstance(event, DoneEvent):
                    self.done.emit(event.final_text)
                elif isinstance(event, ErrorEvent):
                    self.error.emit(event.message)
                    self.done.emit(f"Error: {event.message}")
        except Exception as e:
            self.error.emit(str(e))
            self.done.emit(f"Error: {e}")
