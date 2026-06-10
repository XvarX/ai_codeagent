# Agent 聊天室 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-agent chat rooms where user + spawned agents share a message stream in a floating dialog, with @mention to summon agents.

**Architecture:** Leverages existing AgentMessageQueue and WebSocket event stream. Room messages broadcast to all member agents via parallel enqueue. Agent replies route back via modified stream events carrying `room_id`. Frontend uses floating dialog pattern from CodeEditorDialog.

**Tech Stack:** Python 3.13 backend, Vue 3 + Pinia + Tailwind CSS 4 frontend, WebSocket JSON API

---

### File Structure

| File | Role | Action |
|------|------|--------|
| `agentcore/ws_server.py` | Room WS handlers + `Room` model + stream hook | Modify |
| `agentcore/agent_message_queue.py` | Room message processing in consumer loop | Modify |
| `agentcore/controller.py` | `send_message` accepts optional `room_id` | Modify |
| `ui/src/stores/chat.ts` | Room state (messages, rooms, activeRoomId) | Modify |
| `ui/src/stores/agent.ts` | Agent color assignments | Modify |
| `ui/src/components/AgentPanel.vue` | Embed ChatRoomButton on right | Modify |
| `ui/src/components/ChatRoomButton.vue` | Room pill buttons + create button | Create |
| `ui/src/components/ChatRoomDialog.vue` | Floating chat room window | Create |
| `ui/src/components/CreateRoomDialog.vue` | Modal to pick room name + agents | Create |
| `ui/src/App.vue` | Wire room WS events, mount ChatRoomDialog | Modify |

---

### Task 1: Backend — ChatRoom model + room registry

**Files:** Modify `agentcore/ws_server.py`

- [ ] **Step 1: Add ChatRoom dataclass and room registry**

Add after the `from agentcore.file_browser import FileBrowserHandler` import block (near line 22):

```python
import uuid
from dataclasses import dataclass, field

@dataclass
class ChatRoom:
    id: str
    name: str
    agent_ids: list[str]
    created_at: float = field(default_factory=lambda: __import__('time').time())
```

Inside `_handle_client()` function, just before the message dispatch loop (after `session_mgr` and `store` setup, around line 730), add:

```python
# Room registry (per-session, in-memory)
rooms: dict[str, ChatRoom] = {}
```

- [ ] **Step 2: Verify syntax**

```bash
cd D:/space/labspace/ai_codeagent && python -m py_compile agentcore/ws_server.py
```

Expected: no error output.

- [ ] **Step 3: Commit**

```bash
git add agentcore/ws_server.py
git commit -m "feat: add ChatRoom model and room registry to ws_server"
```

---

### Task 2: Backend — room_create, room_list, room_add_agent, room_destroy handlers

**Files:** Modify `agentcore/ws_server.py`

- [ ] **Step 1: Add room_create handler**

Add after the `select_session` handler (before the `file_list` handler around line 1165):

```python
elif msg_type == "room_create":
    name = msg.get("name", "New Room")
    agent_ids = msg.get("agent_ids", [])
    room = ChatRoom(id=str(uuid.uuid4()), name=name, agent_ids=agent_ids)
    rooms[room.id] = room
    # Add room_id to affected agents' message queue (no message, just context registration)
    await websocket.send(json.dumps({
        "type": "room_created",
        "room": {"id": room.id, "name": room.name, "agent_ids": room.agent_ids, "created_at": room.created_at},
    }, ensure_ascii=False))

elif msg_type == "room_list":
    room_list = [{"id": r.id, "name": r.name, "agent_ids": r.agent_ids, "created_at": r.created_at}
                 for r in rooms.values()]
    await websocket.send(json.dumps({
        "type": "room_list", "rooms": room_list,
    }, ensure_ascii=False))

elif msg_type == "room_add_agent":
    room_id = msg.get("room_id", "")
    agent_id = msg.get("agent_id", "")
    room = rooms.get(room_id)
    if room and agent_id not in room.agent_ids:
        room.agent_ids.append(agent_id)
    await websocket.send(json.dumps({
        "type": "room_updated",
        "room": {"id": room.id, "name": room.name, "agent_ids": room.agent_ids, "created_at": room.created_at},
    }, ensure_ascii=False))

elif msg_type == "room_destroy":
    room_id = msg.get("room_id", "")
    rooms.pop(room_id, None)
    await websocket.send(json.dumps({
        "type": "room_destroyed", "room_id": room_id,
    }, ensure_ascii=False))
```

- [ ] **Step 2: Verify syntax**

```bash
cd D:/space/labspace/ai_codeagent && python -m py_compile agentcore/ws_server.py
```

Expected: no error output.

- [ ] **Step 3: Commit**

```bash
git add agentcore/ws_server.py
git commit -m "feat: add room_create/list/add_agent/destroy WS handlers"
```

---

### Task 3: Backend — room_message handler (broadcast to agent queues)

**Files:** Modify `agentcore/ws_server.py`

- [ ] **Step 1: Add room_message handler**

Add after the handlers from Task 2:

```python
elif msg_type == "room_message":
    room_id = msg.get("room_id", "")
    text = msg.get("text", "")
    room = rooms.get(room_id)
    if not room:
        await websocket.send(json.dumps({
            "type": "error", "message": f"Room {room_id} not found",
        }))
        continue
    slot = session_mgr.get_active()
    if not slot:
        continue
    manager = slot.agent_manager
    # Enqueue to all member agents in parallel
    import asyncio
    for agent_id in room.agent_ids:
        state = manager.agents.get(agent_id)
        if state and state.message_queue:
            formatted = f"[Room: {room.name} | From: 用户]\n{text}"
            state.message_queue.enqueue(formatted, source="room")
```

- [ ] **Step 2: Verify syntax**

```bash
cd D:/space/labspace/ai_codeagent && python -m py_compile agentcore/ws_server.py
```

Expected: no error output.

- [ ] **Step 3: Commit**

```bash
git add agentcore/ws_server.py
git commit -m "feat: add room_message handler — broadcast to agent queues"
```

---

### Task 4: Backend — Inject room_id into stream events

**Files:** Modify `agentcore/controller.py`, Modify `agentcore/ws_server.py`

- [ ] **Step 1: Add room_id to AgentController.send_message**

In `agentcore/controller.py`, modify `send_message` signature (line 158):

```python
async def send_message(self, text: str, room_id: str = "") -> None:
```

Store room context on the agent so event handler can access it. After `self._current_task = asyncio.current_task()`:

```python
self.agent._current_room_id = room_id  # Set by message queue for room messages
```

- [ ] **Step 2: Modify WsEventHandler stream methods to attach room_id**

In `agentcore/ws_server.py`, find the `WsEventHandler` class (around line 27). Modify the stream event methods to check controller's agent for `_current_room_id`:

```python
def _get_room_id(self) -> str:
    """Read room_id from the controller's agent if set."""
    try:
        ctrl = self._controller
        if ctrl and hasattr(ctrl.agent, '_current_room_id'):
            return getattr(ctrl.agent, '_current_room_id', '')
    except Exception:
        pass
    return ""

def _get_agent_id(self) -> str:
    """Read agent_id from the controller's agent if set."""
    try:
        ctrl = self._controller
        if ctrl:
            return getattr(ctrl.agent, '_subagent_id', '')
    except Exception:
        pass
    return ""
```

Then modify `on_text_delta`, `on_thinking`, `on_done`, `on_tool_use`, `on_tool_result` to include `room_id` and `agent_id` when present. Example for `on_text_delta`:

```python
async def on_text_delta(self, token: str, reasoning: bool = False):
    payload = {"type": "text_delta", "token": token, "reasoning": reasoning}
    r = self._get_room_id()
    if r:
        payload["room_id"] = r
        payload["agent_id"] = self._get_agent_id()
    await self._send(payload)
```

Apply same pattern to `on_thinking`, `on_done`, `on_tool_use`, `on_tool_result`.

- [ ] **Step 3: Set _subagent_id on SubagentState's agent during spawn**

In `agentcore/subagent_manager.py`, in the `spawn` method, after creating the AgentController, set:

```python
state.controller.agent._subagent_id = agent_id
```

- [ ] **Step 4: Verify syntax**

```bash
cd D:/space/labspace/ai_codeagent && python -m py_compile agentcore/controller.py && python -m py_compile agentcore/ws_server.py && python -m py_compile agentcore/subagent_manager.py
```

Expected: no error output.

- [ ] **Step 5: Commit**

```bash
git add agentcore/controller.py agentcore/ws_server.py agentcore/subagent_manager.py
git commit -m "feat: inject room_id and agent_id into stream events"
```

---

### Task 5: Backend — _consumer_loop room source branch

**Files:** Modify `agentcore/agent_message_queue.py`

- [ ] **Step 1: Add room_joined tracking to Agent**

In `agentcore/agent.py`, add to `Agent.__init__` (around line 82):

```python
self.room_joined: set[str] = set()
```

- [ ] **Step 2: Add room source branch to _consumer_loop**

In `agentcore/agent_message_queue.py`, modify `_consumer_loop` to add a `source == "room"` branch before the `source == "agent"` branch:

```python
elif source == "room":
    import re
    # Parse room name from prefix: [Room: xxx | From: xxx]\n{text}
    room_match = re.match(r"\[Room: ([^\]]+)\]", text)
    room_name = room_match.group(1).split("|")[0].strip() if room_match else "Unknown"
    from_match = re.search(r"\[From: ([^\]]+)\]", text)
    sender = from_match.group(1).strip() if from_match else "Unknown"
    msg_body = text[text.rfind("]") + 1:].strip() if "]" in text else text

    # Inject room rules on first join (once per room per agent)
    agent = self._controller.agent
    room_key = f"{room_name}"
    if room_key not in agent.room_joined:
        agent.room_joined.add(room_key)
        members = "unknown"
        # The member list isn't available here — ws_server passes it in the text prefix
        # Fallback: check if room info was included
        member_match = re.search(r"\| Members: ([^\]]+)", text)
        if member_match:
            members = member_match.group(1).strip()
        join_notice = (
            f"[System] 你已加入聊天室「{room_name}」。\n"
            f"成员：{members}\n"
            f"规则：被 @提及 时必须回复；未被 @ 时可自行判断是否发言；"
            f"你的 text_delta 回复会自动广播给房间所有成员。"
        )
        agent.messages.append(type('Message', (), {
            'role': 'user',
            'content': join_notice,
        })())

    await self._controller.handler.on_enqueued(sender, msg_body, "room")
```

Actually, let me fix the message appending — use the actual Message type:

```python
from agentcore.core_types import Message

# ... inside the room branch:
if room_key not in agent.room_joined:
    agent.room_joined.add(room_key)
    join_notice = (
        f"[System] 你已加入聊天室「{room_name}」。\n"
        f"成员：{members}\n"
        f"规则：被 @提及 时必须回复；未被 @ 时可自行判断是否发言；"
        f"你的 text_delta 回复会自动广播给房间所有成员。"
    )
    agent.messages.append(Message(role="user", content=join_notice))
```

- [ ] **Step 3: Update ws_server room_message to include member names**

In the `room_message` handler (Task 3), update the formatted message to include member names:

```python
member_names = []
for aid in room.agent_ids:
    st = manager.agents.get(aid)
    member_names.append(st.name if st else aid)
formatted = f"[Room: {room.name} | Members: {', '.join(member_names)} | From: 用户]\n{text}"
state.message_queue.enqueue(formatted, source="room")
```

- [ ] **Step 4: enqueue passes room_id to controller**

In `_consumer_loop`, the final `controller.send_message(text)` call should pass room_id. The room_id must be extracted or passed through. Since the current queue only stores `(text, source)`, add an optional third element:

Modify `enqueue`:

```python
def enqueue(self, text: str, source: str = "user", room_id: str = "") -> None:
    self._queue.put_nowait((text, source, room_id))
    self._ensure_consumer()
```

Modify `_consumer_loop`:

```python
text, source, room_id = await self._queue.get()
```

And in the final send:
```python
async with self._controller._agent_lock:
    await self._controller.send_message(text, room_id=room_id)
```

Update the `room_message` handler in ws_server to pass room_id through enqueue:

```python
state.message_queue.enqueue(formatted, source="room", room_id=room_id)
```

- [ ] **Step 5: Verify syntax and run existing tests**

```bash
cd D:/space/labspace/ai_codeagent && python -m py_compile agentcore/agent_message_queue.py && python -m py_compile agentcore/agent.py && python -m py_compile agentcore/ws_server.py
```

Expected: no error output.

- [ ] **Step 6: Commit**

```bash
git add agentcore/agent_message_queue.py agentcore/agent.py agentcore/ws_server.py
git commit -m "feat: add room source branch to message consumer with rules injection"
```

---

### Task 6: Frontend — Chat store room extensions

**Files:** Modify `ui/src/stores/chat.ts`

- [ ] **Step 1: Add room types and state**

Add after the existing interface definitions:

```typescript
export interface RoomMessage {
  id: string
  roomId: string
  senderId: string   // 'user' for user messages, agentId for agents
  senderName: string
  senderColor: string
  content: string
  timestamp: number
  isStreaming: boolean
}

export interface ChatRoomInfo {
  id: string
  name: string
  agentIds: string[]
  createdAt: number
}
```

Add state inside the store:

```typescript
const roomMessages = ref<Map<string, RoomMessage[]>>(new Map())
const rooms = ref<ChatRoomInfo[]>([])
const activeRoomId = ref<string | null>(null)
let _roomMsgId = 0
```

- [ ] **Step 2: Add room mutation methods**

Add inside the store:

```typescript
function handleRoomCreated(room: ChatRoomInfo) {
  rooms.value = [...rooms.value, room]
}

function handleRoomList(roomList: ChatRoomInfo[]) {
  rooms.value = roomList
}

function handleRoomDestroyed(roomId: string) {
  rooms.value = rooms.value.filter(r => r.id !== roomId)
  roomMessages.value.delete(roomId)
  if (activeRoomId.value === roomId) activeRoomId.value = null
}

function handleRoomUpdated(room: ChatRoomInfo) {
  const idx = rooms.value.findIndex(r => r.id === room.id)
  if (idx >= 0) rooms.value[idx] = room
}

function handleRoomBroadcast(data: { room_id: string; agent_id: string; token: string }) {
  const msgs = roomMessages.value.get(data.room_id) || []
  const agent = useAgentStore()
  const agentInfo = agent.agents.find(a => a.id === data.agent_id)
  const senderName = agentInfo?.name || data.agent_id
  const senderColor = agent.getAgentColor(data.agent_id)

  // Append or create streaming message
  const lastMsg = msgs[msgs.length - 1]
  if (lastMsg && lastMsg.isStreaming && lastMsg.senderId === data.agent_id) {
    lastMsg.content += data.token
  } else {
    msgs.push({
      id: `rm_${++_roomMsgId}`,
      roomId: data.room_id,
      senderId: data.agent_id,
      senderName,
      senderColor,
      content: data.token,
      timestamp: Date.now(),
      isStreaming: true,
    })
  }
  roomMessages.value.set(data.room_id, msgs)
}

function handleRoomThinking(data: { room_id: string; agent_id: string }) {
  // Set thinking state for the member — handled by ChatRoomDialog watching this
}

function handleRoomDone(data: { room_id: string; agent_id: string }) {
  const msgs = roomMessages.value.get(data.room_id) || []
  const lastMsg = msgs[msgs.length - 1]
  if (lastMsg && lastMsg.isStreaming && lastMsg.senderId === data.agent_id) {
    lastMsg.isStreaming = false
  }
  roomMessages.value.set(data.room_id, msgs)
}

function sendRoomMessage(roomId: string, text: string) {
  agentWs.send({ type: 'room_message', room_id: roomId, text })

  // Show user message locally
  const msgs = roomMessages.value.get(roomId) || []
  msgs.push({
    id: `rm_${++_roomMsgId}`,
    roomId,
    senderId: 'user',
    senderName: '你',
    senderColor: '#89b4fa',
    content: text,
    timestamp: Date.now(),
    isStreaming: false,
  })
  roomMessages.value.set(roomId, msgs)
}
```

- [ ] **Step 3: Add methods to return object**

In the return block:

```typescript
return {
  messages, thinking, currentAssistantMsg, diffs, toolLabels,
  maxTokens, usageTokens,
  inputText, insertToInput,
  addUserMessage, startThinking, appendToken, finalizeAssistantMessage,
  addToolResult, addToolCall, addToolResultPreview, addDiff, updateUsage, loadMessages, clear,
  // Room
  roomMessages, rooms, activeRoomId,
  handleRoomCreated, handleRoomList, handleRoomDestroyed, handleRoomUpdated,
  handleRoomBroadcast, handleRoomThinking, handleRoomDone, sendRoomMessage,
}
```

- [ ] **Step 4: Verify TypeScript**

```bash
cd D:/space/labspace/ai_codeagent/ui && npx vue-tsc --noEmit
```

Expected: no error output.

- [ ] **Step 5: Commit**

```bash
git add ui/src/stores/chat.ts
git commit -m "feat: add room state and mutation methods to chat store"
```

---

### Task 7: Frontend — Agent store color assignments

**Files:** Modify `ui/src/stores/agent.ts`

- [ ] **Step 1: Add agent color map**

Add after existing state:

```typescript
const AGENT_COLORS = [
  '#89b4fa', '#a6e3a1', '#f9e2af', '#cba6f7',
  '#f38ba8', '#94e2d5', '#fab387', '#74c7ec',
]
const agentColors = ref<Map<string, string>>(new Map())

function getAgentColor(agentId: string): string {
  if (!agentColors.value.has(agentId)) {
    const idx = agentColors.value.size % AGENT_COLORS.length
    agentColors.value.set(agentId, AGENT_COLORS[idx])
  }
  return agentColors.value.get(agentId)!
}
```

Add `agentColors` and `getAgentColor` to the return block.

- [ ] **Step 2: Verify TypeScript**

```bash
cd D:/space/labspace/ai_codeagent/ui && npx vue-tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add ui/src/stores/agent.ts
git commit -m "feat: add agent color assignment to agent store"
```

---

### Task 8: Frontend — CreateRoomDialog.vue

**Files:** Create `ui/src/components/CreateRoomDialog.vue`

- [ ] **Step 1: Create component**

```vue
<template>
  <Teleport to="body">
    <div class="fixed inset-0 bg-black/50 flex items-center justify-center z-[60]" @click.self="$emit('close')">
      <div class="bg-surface-1 rounded-xl p-5 min-w-[360px] shadow-dialog">
        <h4 class="text-sm font-semibold mb-3 text-text-primary">创建聊天室</h4>

        <label class="text-xs text-text-secondary mb-1 block">房间名</label>
        <input
          v-model="roomName"
          class="w-full p-[6px_10px] border border-border-default rounded-md text-sm mb-3 outline-none bg-surface-2 text-text-primary placeholder:text-text-muted focus:border-accent box-border"
          placeholder="例如：架构讨论"
        />

        <label class="text-xs text-text-secondary mb-1 block">选择成员</label>
        <div class="max-h-[200px] overflow-y-auto mb-4 space-y-1">
          <div
            v-for="agent in availableAgents"
            :key="agent.id"
            class="flex items-center gap-2 px-3 py-2 rounded-md cursor-pointer hover:bg-surface-2 transition-colors duration-200"
            :class="selectedIds.has(agent.id) ? 'bg-accent-subtle' : ''"
            @click="toggleAgent(agent.id)"
          >
            <input type="checkbox" :checked="selectedIds.has(agent.id)" class="pointer-events-none" />
            <span class="text-xs text-text-primary">{{ agent.name }}</span>
            <span class="text-[10px] text-text-muted ml-auto">{{ agent.status }}</span>
          </div>
          <div v-if="availableAgents.length === 0" class="text-xs text-text-muted text-center py-4">
            没有可添加的 Agent，请先 spawn
          </div>
        </div>

        <div class="flex gap-2 justify-end">
          <button
            class="px-4 py-[6px] border-none rounded-md bg-accent text-white cursor-pointer text-[13px] disabled:bg-accent-muted disabled:cursor-not-allowed hover:bg-accent-hover"
            :disabled="!roomName.trim() || selectedIds.size === 0"
            @click="create">创建</button>
          <button
            class="px-4 py-[6px] border border-border-default rounded-md bg-transparent cursor-pointer text-[13px] text-text-primary hover:bg-surface-2"
            @click="$emit('close')">取消</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useAgentStore } from '../stores/agent'
import { agentWs } from '../services/agentWs'

const agentStore = useAgentStore()
const emit = defineEmits<{ close: [] }>()

const roomName = ref('')
const selectedIds = ref(new Set<string>())

const availableAgents = computed(() =>
  agentStore.agents.filter(a => a.status !== 'killed')
)

function toggleAgent(id: string) {
  const next = new Set(selectedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedIds.value = next
}

function create() {
  agentWs.send({
    type: 'room_create',
    name: roomName.value.trim(),
    agent_ids: [...selectedIds.value],
  })
  emit('close')
}
</script>
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd D:/space/labspace/ai_codeagent/ui && npx vue-tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add ui/src/components/CreateRoomDialog.vue
git commit -m "feat: add CreateRoomDialog component"
```

---

### Task 9: Frontend — ChatRoomButton.vue

**Files:** Create `ui/src/components/ChatRoomButton.vue`

- [ ] **Step 1: Create component**

```vue
<template>
  <div class="flex items-center gap-1.5 ml-2 pl-2 border-l border-border-subtle">
    <span class="text-[10px] text-text-muted">💬</span>
    <button
      v-for="room in chatStore.rooms"
      :key="room.id"
      class="px-2.5 py-1 rounded-md text-xs cursor-pointer border-none whitespace-nowrap transition-colors duration-200"
      :class="chatStore.activeRoomId === room.id
        ? 'bg-accent-subtle text-accent'
        : 'bg-surface-2 text-text-secondary hover:bg-surface-3'"
      @click="openRoom(room.id)"
    >{{ room.name }}
      <span class="text-[10px] text-text-muted ml-1">({{ room.agentIds.length }})</span>
    </button>
    <button
      class="bg-transparent border border-dashed border-border-default rounded-md px-2 py-1 cursor-pointer text-xs text-accent hover:bg-surface-2"
      @click="showCreate = true"
    >+ 新建</button>
    <CreateRoomDialog v-if="showCreate" @close="showCreate = false" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useChatStore } from '../stores/chat'
import { agentWs } from '../services/agentWs'
import CreateRoomDialog from './CreateRoomDialog.vue'

const chatStore = useChatStore()
const showCreate = ref(false)

onMounted(() => {
  agentWs.send({ type: 'room_list' })
})

function openRoom(id: string) {
  chatStore.activeRoomId = id
}
</script>
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd D:/space/labspace/ai_codeagent/ui && npx vue-tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add ui/src/components/ChatRoomButton.vue
git commit -m "feat: add ChatRoomButton component"
```

---

### Task 10: Frontend — ChatRoomDialog.vue

**Files:** Create `ui/src/components/ChatRoomDialog.vue`

- [ ] **Step 1: Create component**

```vue
<template>
  <Teleport to="body">
    <div v-if="room" class="fixed flex flex-col bg-surface-1 border border-border-default rounded-lg"
      :style="{ left: dialogX + 'px', top: dialogY + 'px', width: dialogWidth + 'px',
                height: dialogHeight + 'px', zIndex: 50,
                boxShadow: maximized ? 'none' : '0 8px 32px rgba(0,0,0,0.12)',
                borderRadius: maximized ? '0' : undefined,
                transition: maximized ? 'left 0.15s, top 0.15s, width 0.15s, height 0.15s' : undefined }"
      :class="maximized ? '' : 'rounded-lg'">

      <!-- Title bar -->
      <div class="flex items-center bg-surface-2 border-b border-border-default cursor-move shrink-0 px-3 py-1.5"
        @mousedown.prevent="startDrag" @dblclick.prevent="toggleMaximize">
        <span class="text-xs text-text-primary font-medium">💬 {{ room.name }}</span>
        <span class="text-[10px] text-text-muted ml-2">{{ room.agentIds.length + 1 }} 人</span>
        <div class="flex-1"></div>
        <button class="bg-transparent border-none text-text-muted hover:text-text-primary text-sm cursor-pointer px-1"
          @click.stop="chatStore.activeRoomId = null">✕</button>
      </div>

      <!-- Body: sidebar + chat -->
      <div class="flex flex-1 overflow-hidden">
        <!-- Member list -->
        <div class="w-[140px] border-r border-border-subtle p-2 flex flex-col gap-1 shrink-0 overflow-y-auto">
          <div class="flex items-center gap-1.5 px-2 py-1 rounded text-xs text-text-primary">
            <span class="w-1.5 h-1.5 rounded-full bg-blue-400 shrink-0"></span>
            <span>👤 你</span>
          </div>
          <div v-for="agent in memberAgents" :key="agent.id"
            class="flex items-center gap-1.5 px-2 py-1 rounded text-xs hover:bg-surface-2 transition-colors duration-200">
            <span class="w-1.5 h-1.5 rounded-full shrink-0"
              :class="agent.status === 'running' ? 'bg-success' : 'bg-text-muted'"></span>
            <span :style="{ color: agent.color }">{{ agent.name }}</span>
          </div>
        </div>

        <!-- Message stream -->
        <div class="flex-1 flex flex-col overflow-hidden">
          <div ref="msgContainer" class="flex-1 overflow-y-auto p-3 flex flex-col gap-3">
            <div v-for="msg in messages" :key="msg.id" class="flex"
              :class="msg.senderId === 'user' ? 'justify-end' : 'justify-start'">
              <div class="flex flex-col max-w-[75%]">
                <span v-if="msg.senderId !== 'user'" class="text-[10px] mb-0.5"
                  :style="{ color: msg.senderColor }">@{{ msg.senderName }}</span>
                <div class="px-3 py-2 rounded-xl text-xs whitespace-pre-wrap break-all"
                  :class="msg.senderId === 'user'
                    ? 'bg-accent text-white rounded-br-sm'
                    : 'bg-surface-3 text-text-primary rounded-bl-sm'">
                  {{ msg.content }}
                  <span v-if="msg.isStreaming" class="inline-block w-1.5 h-3.5 bg-text-muted animate-pulse ml-0.5 align-middle"></span>
                </div>
              </div>
            </div>
          </div>

          <!-- Input -->
          <div class="px-3 py-2 border-t border-border-subtle flex gap-2">
            <input
              v-model="inputText"
              class="flex-1 bg-surface-2 border border-border-default rounded-md px-3 py-2 text-sm text-text-primary outline-none focus:border-accent min-h-[44px]"
              placeholder="@name 或输入消息..."
              @keydown.ctrl.enter="send"
              @keydown.enter="send"
            />
            <button class="bg-accent text-white text-xs px-4 py-2 rounded-md cursor-pointer hover:bg-accent-hover border-none"
              @click="send">发送</button>
          </div>
        </div>
      </div>

      <!-- Resize handle -->
      <div v-if="!maximized" class="h-2 cursor-ns-resize hover:bg-accent/20 shrink-0"
        @mousedown.prevent="startResize($event, 'vertical')"></div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useChatStore } from '../stores/chat'
import { useAgentStore } from '../stores/agent'

const chatStore = useChatStore()
const agentStore = useAgentStore()

const dialogX = ref(80)
const dialogY = ref(80)
const dialogWidth = ref(700)
const dialogHeight = ref(500)
const minWidth = 400
const minHeight = 300
const maximized = ref(false)
const savedRect = { x: 80, y: 80, w: 700, h: 500 }
const inputText = ref('')
const msgContainer = ref<HTMLElement | null>(null)

const room = computed(() =>
  chatStore.rooms.find(r => r.id === chatStore.activeRoomId) || null
)

const messages = computed(() =>
  chatStore.roomMessages.get(chatStore.activeRoomId ?? '') || []
)

const memberAgents = computed(() => {
  if (!room.value) return []
  return room.value.agentIds.map(id => {
    const agent = agentStore.agents.find(a => a.id === id)
    return {
      id,
      name: agent?.name || id,
      status: agent?.status || 'idle',
      color: agentStore.getAgentColor(id),
    }
  })
})

function send() {
  const text = inputText.value.trim()
  if (!text || !chatStore.activeRoomId) return
  chatStore.sendRoomMessage(chatStore.activeRoomId, text)
  inputText.value = ''
}

watch(() => messages.value.length, () => {
  nextTick(() => {
    if (msgContainer.value) {
      msgContainer.value.scrollTop = msgContainer.value.scrollHeight
    }
  })
})

function toggleMaximize() {
  if (maximized.value) {
    dialogX.value = savedRect.x; dialogY.value = savedRect.y
    dialogWidth.value = savedRect.w; dialogHeight.value = savedRect.h
    maximized.value = false
  } else {
    savedRect.x = dialogX.value; savedRect.y = dialogY.value
    savedRect.w = dialogWidth.value; savedRect.h = dialogHeight.value
    const chatArea = document.getElementById('chat-area')
    if (chatArea) {
      const rect = chatArea.getBoundingClientRect()
      dialogX.value = rect.left; dialogY.value = rect.top
      dialogWidth.value = rect.width; dialogHeight.value = rect.height
    } else {
      dialogX.value = 0; dialogY.value = 40
      dialogWidth.value = window.innerWidth; dialogHeight.value = window.innerHeight - 96
    }
    maximized.value = true
  }
}

function startDrag(e: MouseEvent) {
  if (maximized.value) return
  const startX = e.clientX, startY = e.clientY
  const origX = dialogX.value, origY = dialogY.value
  function onMove(ev: MouseEvent) {
    dialogX.value = origX + (ev.clientX - startX)
    dialogY.value = Math.max(0, origY + (ev.clientY - startY))
  }
  function onUp() {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

function startResize(e: MouseEvent, dir: string) {
  const startX = e.clientX, startY = e.clientY
  const origW = dialogWidth.value, origH = dialogHeight.value
  function onMove(ev: MouseEvent) {
    if (dir === 'horizontal') {
      dialogWidth.value = Math.max(minWidth, origW + (ev.clientX - startX))
    } else {
      dialogHeight.value = Math.max(minHeight, origH + (ev.clientY - startY))
    }
  }
  function onUp() {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}
</script>
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd D:/space/labspace/ai_codeagent/ui && npx vue-tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add ui/src/components/ChatRoomDialog.vue
git commit -m "feat: add ChatRoomDialog floating chat room component"
```

---

### Task 11: Frontend — AgentPanel.vue embedding

**Files:** Modify `ui/src/components/AgentPanel.vue`

- [ ] **Step 1: Add ChatRoomButton to AgentPanel**

In the `<div class="flex items-center h-9 px-2 gap-1 flex-shrink-0">`, after `<div class="flex-1"></div>`, add:

```vue
<ChatRoomButton />
```

Import at the top of `<script setup>`:

```typescript
import ChatRoomButton from './ChatRoomButton.vue'
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd D:/space/labspace/ai_codeagent/ui && npx vue-tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add ui/src/components/AgentPanel.vue
git commit -m "feat: embed ChatRoomButton in AgentPanel"
```

---

### Task 12: Frontend — App.vue event registration

**Files:** Modify `ui/src/App.vue`

- [ ] **Step 1: Add room event listeners and mount ChatRoomDialog**

Add `ChatRoomDialog` import:

```typescript
import ChatRoomDialog from './components/ChatRoomDialog.vue'
```

In the template, add after `<CodeEditorDialog />`:

```vue
<ChatRoomDialog />
```

In `onMounted`, add event listeners after the file browser section:

```typescript
// Chat room events
agentWs.on('room_created', (d: any) => chatStore.handleRoomCreated(d.room))
agentWs.on('room_list', (d: any) => chatStore.handleRoomList(d.rooms))
agentWs.on('room_destroyed', (d: any) => chatStore.handleRoomDestroyed(d.room_id))
agentWs.on('room_updated', (d: any) => chatStore.handleRoomUpdated(d.room))
agentWs.on('room_broadcast', (d: any) => chatStore.handleRoomBroadcast(d))
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd D:/space/labspace/ai_codeagent/ui && npx vue-tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add ui/src/App.vue
git commit -m "feat: register room events and mount ChatRoomDialog in App"
```

---

### Task 13: Integration smoke test

**Files:** None (manual test)

- [ ] **Step 1: Start backend**

```bash
python -m agentcore.main --ws --port 18765
```

- [ ] **Step 2: Start frontend**

```bash
cd ui && npm run dev
```

- [ ] **Step 3: Manual test checklist**

1. Spawn 2 sub-agents via Agent Bar
2. Click "+ 新建" in chat room section
3. Create a room with both agents
4. Room button appears in Agent Bar
5. Click room button → floating ChatRoomDialog opens
6. Type a message → both agents receive it in their queue
7. Agents stream text_delta responses → appear in room message stream with @name + color
8. @mention an agent → agent responds
9. Double-click title bar → maximizes to chat area
10. Close room → dialog closes

- [ ] **Step 4: Commit (if needed)**

```bash
git commit -m "test: integration smoke test passed for agent chat room"
```
