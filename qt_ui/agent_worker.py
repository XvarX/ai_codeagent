"""QThread worker that runs Agent.run() and emits progress signals."""

import asyncio

from PySide6.QtCore import QThread, Signal


class AgentWorker(QThread):
    """Runs Agent.run() in a worker thread with callback signals."""

    thinking = Signal()
    tool_call = Signal(str, str)      # name, input_json
    tool_result = Signal(str, str, bool)  # name, result, is_error
    response = Signal(str, str)       # raw_json, text
    done = Signal(str)                # final_text
    error = Signal(str)

    def __init__(self, agent, user_message: str, parent=None):
        super().__init__(parent)
        self.agent = agent
        self.user_message = user_message

    def run(self):
        # Temporarily install callbacks on the agent
        self.agent.on_thinking = self._on_thinking
        self.agent.on_tool_call = self._on_tool_call
        self.agent.on_tool_result = self._on_tool_result
        self.agent.on_response = self._on_response

        try:
            result = asyncio.run(self.agent.run(self.user_message))
            self.done.emit(result)
        except Exception as e:
            self.error.emit(str(e))
            self.done.emit(f"Error: {e}")

    async def _on_thinking(self):
        self.thinking.emit()

    async def _on_tool_call(self, name: str, input: dict):
        import json
        self.tool_call.emit(name, json.dumps(input, ensure_ascii=False))

    async def _on_tool_result(self, name: str, result: str, is_error: bool):
        self.tool_result.emit(name, result, is_error)

    async def _on_response(self, text: str, tool_use_blocks: list, raw: dict):
        import json
        # Attach tool blocks to raw for downstream
        raw["_tool_use_blocks"] = [
            {"tool_name": t.tool_name, "tool_use_id": t.tool_use_id, "input": t.input}
            for t in tool_use_blocks
        ]
        self.response.emit(
            json.dumps(raw, ensure_ascii=False),
            text,
        )
