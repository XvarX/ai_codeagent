# Agent Message Queue 设计

日期：2026-06-02

## 背景

当前 agent 的消息入口有三个，互不协调：

1. **用户输入框** — `_on_send()` → `page.run_task(send_message)`，无队列，可并发
2. **Inbox poller** — 每 1s 轮询 `asyncio.Queue`，有空窗期
3. **`run_stream` 内 inbox drain** — 每轮循环开始时 drain，消息直接塞进 messages

问题：用户或 agent 间消息到达时，如果 agent 正在处理上一条，可能并发执行 `send_message`，破坏消息历史的一致性。

## 方案

每个 agent（master 和 subagent）持有一个 `AgentMessageQueue` 实例，统一所有消息入口，顺序执行。

## 核心类

```python
class AgentMessageQueue:
    """Per-agent sequential message queue."""

    def __init__(self, controller: AgentController):
        self._queue: asyncio.Queue[tuple[str, str]] = None  # (text, source)
        self._controller = controller
        self._consumer_task: asyncio.Task | None = None

    def enqueue(self, text: str, source: str = "user"):
        """入队。如果消费者没跑就启动。"""

    async def _consumer_loop(self):
        """持续取消息，send_message 阻塞到完成后再取下一条。"""

    def cancel(self):
        """停止消费者。"""
```

消费逻辑：

```python
async def _consumer_loop(self):
    while True:
        text, source = await self._queue.get()
        await self._controller.send_message(text)  # 阻塞到整轮结束
```

- 队列为空时 `_consumer_loop` 挂在 `queue.get()` 上，不消耗 CPU
- `send_message` 返回 = run_stream 完成 = Final Response + DoneEvent 已触发
- 下一条消息自动开始，无需 poller 或事件监听

## 改动清单

### 新增

- `agent_message_queue.py` — `AgentMessageQueue` 类

### 修改

| 文件 | 改动 |
|---|---|
| `subagent_manager.py` | `_create_master` 和 `spawn` 里创建 queue，替代 `inbox`；删 `_inbox_poller` |
| `flet_ui/app.py` | `_on_send` 改为 `queue.enqueue()`；删 `_on_inbox_message` 相关转发 |
| `tools/send_message_tool.py` | `call` 改为 `target_queue.enqueue()` |
| `controller.py` | `AgentController` 持有 `message_queue` 引用；`send_message` 不再被 UI 直接调用 |
| `agent.py` | 删 `inbox` 属性，删 `run_stream` 里的 inbox drain 逻辑 |
| `events.py` | 删 `InboxMessageEvent` |

### 删除

- `Agent.inbox`
- `SubagentManager._inbox_poller()`
- `run_stream` 内的 inbox drain 代码块
- `InboxMessageEvent`
- `controller.py` 中 `InboxMessageEvent` 的分发逻辑
- `app.py` 中 `_on_inbox_message`、`_fwd_inbox_msg` 相关代码

## 消息流（改后）

```
用户输入 → _on_send() → queue.enqueue(text)
                                ↓
Agent 间  → SendMessageTool → target_queue.enqueue(text)
                                ↓
                    _consumer_loop 取消息
                                ↓
                    controller.send_message(text)
                                ↓
                    run_stream → events → handler → UI
                                ↓
                    send_message 返回（整轮结束）
                                ↓
                    取下一条消息...
```

## UI 行为

- agent 处理中时用户可继续输入，消息排队
- 输入栏不锁定
- Chat view 在每条消息处理开始时才 `add_user_message`

## Handler 回调

`_SubagentHandler` 的 `_fwd_inbox_msg` 和 `on_inbox_message` 删除。
新增 `on_enqueued` 回调（可选），用于在消息入队时通知 UI 显示"排队中"提示。
