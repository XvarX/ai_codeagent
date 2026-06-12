# Chatroom Panel Immediate Push Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 聊天室面板 (`roomMessages`) 不经过活跃 agent 消息队列，直接接收 BroadcastRoom 消息实现立即显示，主聊天区 (`messages`) 保持现有排序逻辑不变。

**Architecture:** 新增 `room_chat` WebSocket 事件，通过 `mgr.ws_handler` 全局 handler 即时推送。后端 BroadcastRoom 调用时同时走两条路径：入队（主聊天排序 + 持久化）和 `room_chat` 即时推送（聊天室面板展示）。前端新增 `handleRoomChat` 只写 `roomMessages`，`handleRoomRelay` 移除 `roomMessages` 写入。

**Tech Stack:** Python (asyncio + websockets), TypeScript (Vue 3 + Pinia)

---

### Task 1: 后端 — BroadcastRoomTool 新增 room_chat 即时推送

**Files:**
- Modify: `agentcore/tools/broadcast_room_tool.py:163-188`

- [ ] **Step 1: 在 relay 入队循环后新增 room_chat 推送**

将 `ws_handler = agent_state.controller.handler` 提前到 `self.suppress_reply = True` 之前，并在其下方新增 room_chat 推送逻辑：

```python
        self.suppress_reply = True  # success → suppress LLM follow-up

        # Push to frontend via THIS agent's own handler. Only the active
        # agent's handler (WsEventHandler) has _send — non-active agents
        # use _AgentHandler which doesn't, so their broadcasts reach the
        # frontend only when the active agent dequeues them in consumer_loop.
        ws_handler = agent_state.controller.handler

        # Push to chatroom panel immediately via manager's global ws_handler.
        # This bypasses the active agent's message queue so the chatroom panel
        # shows messages from non-active agents without waiting for the active
        # agent to finish its current turn.
        mgr_ws = mgr.ws_handler
        if mgr_ws and hasattr(mgr_ws, "_send") and mgr_ws is not ws_handler:
            try:
                await mgr_ws._send({
                    "type": "room_chat",
                    "room_id": room_id,
                    "room_name": room.name,
                    "from_name": from_name,
                    "from_id": self._from_id,
                    "text": message,
                    "reply_to": reply_to,
                })
            except Exception:
                pass
```

同时删除原来第166-169行的注释和第170行的 `ws_handler = agent_state.controller.handler`（已上移）。

- [ ] **Step 2: 运行现有测试确认不破坏已有功能**

```bash
pytest agentcore/tests/test_broadcast_room.py -v
```

Expected: 全部 PASS（`test_broadcast_success` 中的活跃 agent 场景走 `ws_handler is mgr_ws` 分支，不会重复推送）

---

### Task 2: 测试 — 验证非活跃 agent room_chat 推送

**Files:**
- Modify: `agentcore/tests/test_broadcast_room.py`

- [ ] **Step 1: 新增测试用例 test_broadcast_room_chat_for_inactive_agent**

在文件末尾添加：

```python
@pytest.mark.asyncio
async def test_broadcast_room_chat_for_inactive_agent():
    """Non-active agent's BroadcastRoom sends room_chat via mgr.ws_handler."""
    room = _make_room("r1", "Room1", ["A", "B", "C"])
    state_a = _make_agent_state("A", "Alice")
    state_a.controller.agent._current_room_id = "r1"
    state_b = _make_agent_state("B", "Bob")
    # Agent A is NOT the active agent — no WsEventHandler, no _send on handler
    state_a.controller.handler = MagicMock()
    del state_a.controller.handler._send  # _AgentHandler has no _send
    state_b.controller.handler = MagicMock()
    del state_b.controller.handler._send

    # Global ws_handler has _send (active agent's handler)
    ws_handler = MagicMock()
    ws_handler._send = AsyncMock()

    mgr = _make_manager(
        rooms={"r1": room},
        agents={"A": state_a, "B": state_b},
    )
    mgr.ws_handler = ws_handler

    tool = BroadcastRoomTool(mgr, "A")
    ctx = ToolContext(cwd="/tmp", messages=[])

    result = await tool.call({"message": "Hello from inactive!"}, ctx)
    assert "1" in result  # broadcast to 1 member (B only)

    # mgr.ws_handler._send called with room_chat (immediate chatroom panel push)
    calls = [c[0][0] for c in ws_handler._send.call_args_list]
    chat_events = [c for c in calls if c["type"] == "room_chat"]
    assert len(chat_events) == 1
    assert chat_events[0]["room_id"] == "r1"
    assert chat_events[0]["from_id"] == "A"
    assert chat_events[0]["text"] == "Hello from inactive!"
```

- [ ] **Step 2: 运行新测试确认通过**

```bash
pytest agentcore/tests/test_broadcast_room.py::test_broadcast_room_chat_for_inactive_agent -v
```

Expected: PASS

- [ ] **Step 3: 运行全部测试**

```bash
pytest agentcore/tests/test_broadcast_room.py -v
```

Expected: 全部 PASS

---

### Task 3: 前端 — 新增 handleRoomChat，移除 handleRoomRelay 中的 roomMessages 写入

**Files:**
- Modify: `ui/src/stores/chat.ts:293-346` (handleRoomRelay)
- Add: `handleRoomChat` 函数

- [ ] **Step 1: 在 handleRoomRelay 中移除 roomMessages 写入**

将第293-346行的 `handleRoomRelay` 函数，删除第331-345行的 roomMessages 写入部分：

```typescript
  function handleRoomRelay(data: { room_id: string; room_name: string; from_name: string; from_id: string; text: string; reply_to: string }) {
    const agent = useAgentStore()

    // Deduplicate: same broadcast may arrive twice (once from BroadcastRoom,
    // once from _consumer_loop).  Only process the first.
    const dedupeKey = `${data.room_id}:${data.from_id}:${data.text}`
    if (_roomRelaySeen.has(dedupeKey)) return
    _roomRelaySeen.add(dedupeKey)
    if (_roomRelaySeen.size > 200) {
      const iter = _roomRelaySeen.values()
      for (let i = 0; i < 100; i++) _roomRelaySeen.delete(iter.next().value)
    }

    const isActiveAgent = data.from_id === agent.activeAgentId
    const relayMsg: ChatMessage = {
      role: (isActiveAgent ? 'assistant' : 'user') as 'user' | 'assistant',
      content: data.text,
      roomInfo: {
        roomId: data.room_id,
        roomName: data.room_name,
        senderName: data.from_name,
        senderId: data.from_id,
        direction: 'in' as const,
        replyTo: data.reply_to || undefined,
      },
    }

    // Active agent's own broadcast → show immediately.
    // Other agents' broadcasts when active agent is busy → buffer.
    // Other agents' broadcasts when active agent is idle → show immediately.
    if (isActiveAgent) {
      messages.value.push(relayMsg)
    } else if (_busyCounter > 0) {
      _relayBuffer.push(relayMsg)
    } else {
      messages.value.push(relayMsg)
    }
  }
```

- [ ] **Step 2: 新增 handleRoomChat 函数**

在 `handleRoomRelay` 之后、`sendRoomMessage` 之前（第346行前）插入：

```typescript
  function handleRoomChat(data: { room_id: string; room_name: string; from_name: string; from_id: string; text: string; reply_to: string }) {
    if (!data.room_id) return
    const agent = useAgentStore()
    const msgs = roomMessages.value.get(data.room_id) || []
    msgs.push({
      id: `rm_${++_roomMsgId}`,
      roomId: data.room_id,
      senderId: data.from_id,
      senderName: data.from_name,
      senderColor: agent.getAgentColor(data.from_id),
      content: data.text,
      timestamp: Date.now(),
      isStreaming: false,
    })
    _setRoomMessages(data.room_id, msgs)
  }
```

- [ ] **Step 3: 在 return/export 中暴露 handleRoomChat**

在文件末尾的 return 对象（约第380-395行）中添加 `handleRoomChat`：

在 `handleRoomRelay,` 下一行添加 `handleRoomChat,`

---

### Task 4: 前端 — App.vue 中注册 room_chat 事件监听

**Files:**
- Modify: `ui/src/App.vue:284`

- [ ] **Step 1: 注册 room_chat 事件监听**

在第284行 `agentWs.on('room_relay', ...)` 之后添加：

```typescript
  agentWs.on('room_chat', (d: any) => chatStore.handleRoomChat(d));
```

---

### Task 5: 提交

- [ ] **Step 1: 提交所有变更**

```bash
git add agentcore/tools/broadcast_room_tool.py \
        agentcore/tests/test_broadcast_room.py \
        ui/src/stores/chat.ts \
        ui/src/App.vue
git commit -m "feat: push BroadcastRoom messages to chatroom panel immediately via room_chat event"

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```
```
