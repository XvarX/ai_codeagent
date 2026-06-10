# Agent 聊天室 — 设计文档

## 概述

在现有 Agent 系统中新增「聊天室」功能。用户可创建房间、拉入已 spawned Agent，房间内所有成员（用户+Agent）共享消息流。Agent 被 @ 时必须回复，未被 @ 时可自行判断是否插话。

## UI 架构

### 组件树

```
AgentPanel.vue (改造)
  ├─ Agent 标签 (现有)
  └─ ChatRoomButton.vue (新增) ← 右侧
       ├─ 已有房间按钮列表
       └─ + 新建按钮
            └─ CreateRoomDialog.vue (新增，弹窗选 Agent)

ChatRoomDialog.vue (新增，浮窗)
  ├─ 标题栏 (可拖拽，双击最大化覆盖 #chat-area)
  ├─ 左侧成员列表 (状态指示灯)
  ├─ 右侧消息流 (@agent 彩色气泡)
  └─ 底部输入栏
```

### 交互行为

| 交互 | 行为 |
|------|------|
| 点击 Agent Bar 右侧房间按钮 | 打开/切换到对应 ChatRoomDialog 浮窗 |
| 点击 + 新建 | 弹出 CreateRoomDialog |
| 双击 ChatRoomDialog 标题栏 | 最大化（仅覆盖 `#chat-area`），右下角 `▣` 恢复 |
| 拖拽标题栏 | 移动浮窗位置 |
| 拖拽右下角 | 调整浮窗大小（最小 400×300，默认 700×500）|
| 发送消息 | Ctrl+Enter 或点击发送按钮 |
| @提及 | `@agent名` 触发提及，被@的 Agent 必须回复 |

### 设计 Token

复用项目现有 Tailwind 变量：`surface-0` ~ `surface-4`、`accent`、`text-primary/secondary/muted`、`border-default/subtle`、`success`、`warning`、`danger`。

**Agent 颜色分配**（循环）：`#89b4fa` `#a6e3a1` `#f9e2af` `#cba6f7` `#f38ba8` `#94e2d5` `#fab387` `#74c7ec`

### 消息气泡规格

| 发送者 | 对齐 | 背景色 | 标签 |
|--------|------|--------|------|
| 用户 | 右对齐 | `accent` (蓝) | 无 |
| Agent | 左对齐 | `surface-3` | `@agent名` + Agent 颜色 |
| 系统消息 | 居中 | 透明 | 灰色文字 (Agent 加入/离开/房间创建) |

## 数据模型

### 后端 (Python 内存结构)

```python
@dataclass
class ChatRoom:
    id: str          # uuid
    name: str
    agent_ids: list[str]  # SubagentState.id 列表
    created_at: float     # timestamp

# session 级别存储，不持久化
rooms: dict[str, ChatRoom] = {}
```

### 前端 Store 扩展

```typescript
// chat.ts store 新增
interface RoomMessage {
  id: string
  roomId: string
  sender: { id: string; name: string; color: string }  // sender.id='user' 表示用户
  content: string
  timestamp: number
  isStreaming: boolean  // 流式输出中
}

roomMessages: Map<string, RoomMessage[]>  // roomId -> messages
activeRoomId: string | null               // 当前打开的浮窗房间
rooms: ChatRoomInfo[]                     // 房间列表

// ChatRoomInfo
interface ChatRoomInfo {
  id: string
  name: string
  agentIds: string[]
  createdAt: number
}
```

## WebSocket API

### 新增消息类型

| type | 方向 | 参数 | 响应 |
|------|------|------|------|
| `room_create` | C→S | `{name, agent_ids}` | `{type:"room_created", room}` |
| `room_list` | C→S | `{}` | `{type:"room_list", rooms}` |
| `room_message` | C→S | `{room_id, text}` | 广播到各 Agent 队列 |
| `room_broadcast` | S→C | `{room_id, sender, text_delta}` | Agent 回复推入房间消息流 |
| `room_add_agent` | C→S | `{room_id, agent_id}` | `{type:"room_updated", room}` |
| `room_destroy` | C→S | `{room_id}` | `{type:"room_destroyed", room_id}` |

### 事件流路由

现有流式事件增加 `room_id` 和 `agent_id` 字段：

```json
// Agent 在房间上下文中回复
{"type": "text_delta", "token": "建议", "room_id": "xxx", "agent_id": "yyy"}
{"type": "thinking", "room_id": "xxx", "agent_id": "yyy"}
{"type": "done", "room_id": "xxx", "agent_id": "yyy"}
```

前端根据 `room_id` 将事件路由到对应 ChatRoomDialog 的消息流，而非 global chat。

## Agent 回复路由

### 发送端 (room_message handler)

```
用户输入 → ws: room_message {room_id, text}
  → 遍历 room.agent_ids
  → 每个 agent 的 message_queue.enqueue(text, source="room")
  → 并行 enqueue，不等待回复
```

### 接收端 (Agent 消费队列)

Agent 的 `_consumer_loop` 处理 `source="room"` 消息：
- 注入系统提示：`"你在聊天室 '{room_name}' 中，成员: [列表]。@提及你必须回复，否则自行判断。"`
- 调用 `controller.send_message(text)` 进入 Agent 的 while-true 循环
- 流式输出 text_delta 通过 WebSocket 推送，附加 `room_id` + `agent_id`

### Agent 间通信（房间内）

Agent 在房间内的 `text_delta` 流式回复自动广播到房间（通过 room_id 路由）。
Agent 调用 `SendMessage` 工具时：
- 如果目标在**同一房间** → 私信，不进房间消息流
- 如果目标是**房间外 Agent** → 正常私信
- 禁止广播到整个房间（`to: "*"` 在房间内无效，用 text_delta 即可）

### 前后端事件映射

| 后端事件 | 前端处理 |
|----------|----------|
| `text_delta {room_id, agent_id, token}` | 追加到 `roomMessages[roomId]` 最后一条消息的 content，标记 `isStreaming: true` |
| `thinking {room_id, agent_id}` | 成员列表中该 Agent 显示思考动画 |
| `done {room_id, agent_id}` | 标记 `isStreaming: false`，消息完成 |
| `tool_use/tool_result` (带 room_id) | 渲染为消息气泡内的可折叠工具卡片 |

## 现有代码改动清单

### 后端

| 文件 | 改动 |
|------|------|
| `agentcore/ws_server.py` | 新增 `room_create/list/message/add_agent/destroy` 消息处理；现有流式事件增加 room_id 路由 |
| `agentcore/agent_message_queue.py` | `_consumer_loop` 增加 `source="room"` 分支，注入房间上下文 |
| `agentcore/subagent_manager.py` | `send_message_to_agent` 已满足需求，无需改动 |
| `agentcore/controller.py` | `send_message` 增加 `room_id` 参数透传 |

### 前端

| 文件 | 改动 |
|------|------|
| `ui/src/stores/chat.ts` | 新增 `roomMessages`、`rooms`、`activeRoomId`；`onRoomBroadcast` 方法 |
| `ui/src/stores/agent.ts` | 新增 `agentColors: Map<id, color>` |
| `ui/src/components/AgentPanel.vue` | 右侧嵌入 `<ChatRoomButton />` |
| `ui/src/components/ChatRoomButton.vue` | **新建** — 房间按钮组 |
| `ui/src/components/ChatRoomDialog.vue` | **新建** — 房间浮窗 |
| `ui/src/components/CreateRoomDialog.vue` | **新建** — 创建房间弹窗 |
| `ui/src/App.vue` | 注册 `room_*` 事件监听；挂载 ChatRoomDialog |

## 设计规范

### 浮窗 z-index: 50（与 CodeEditorDialog 同级）
### 拖拽/最大化逻辑复用 CodeEditorDialog 已有实现
### 消息气泡圆角 8px，间距 12px
### 成员列表宽 140px，状态指示 6px 圆点
### Agent 颜色循环分配，房间创建时确定
### 所有可点击元素 cursor-pointer
### 输入框 44px 最小高度（触控友好）
### 过渡动画 200ms ease
