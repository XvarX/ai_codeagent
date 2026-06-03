# Vue-Flet 功能对齐实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐 Vue 前端相比 Flet 前端缺失的功能，使两者在用户体验上完全对齐。

**Architecture:** Vue 前端通过 WebSocket 与 Python 后端通信（`agentcore/ws_server.py`）。大部分缺失功能只需前端改动，少数需要后端补充 WS 消息处理。所有事件类型后端已支持，前端只需正确消费。

**Tech Stack:** Vue 3 + TypeScript + Pinia + marked, Python 3 + websockets

---

## 文件结构

| 文件 | 职责 | 改动类型 |
|---|---|---|
| `ui/src/App.vue` | WS 事件路由、全局状态 | 修改 |
| `ui/src/stores/chat.ts` | 聊天消息、toolCalls 数据 | 修改 |
| `ui/src/stores/agent.ts` | compacting 状态 | 修改 |
| `ui/src/stores/debug.ts` | 调试条目、clear 保留 System | 修改 |
| `ui/src/components/ChatView.vue` | 渲染聊天、tool 标签 | 修改 |
| `ui/src/components/InputBar.vue` | 输入框、compacting 禁用 | 修改 |
| `ui/src/components/ConfigDialog.vue` | Provider 下拉、高级设置 | 修改 |
| `ui/src/components/McpDialog.vue` | Server 状态、操作按钮 | 修改 |
| `ui/src/components/AgentSidebar.vue` | 折叠动画、状态颜色 | 修改 |
| `ui/src/components/DebugDrawer.vue` | 折叠模式、Compact 状态 | 修改 |
| `ui/src/components/SkillDialog.vue` | 结构化技能卡片 | 修改 |
| `agentcore/ws_server.py` | MCP stop/restart 消息 | 修改 |

---

### Task 1: 聊天面板显示工具调用标签

**参考 Flet:** `flet_ui/app.py` `_on_tool_use` + `_on_tool_result` 在聊天流内显示紧凑标签

**Files:**
- Modify: `ui/src/stores/chat.ts`
- Modify: `ui/src/components/ChatView.vue`
- Modify: `ui/src/App.vue`

- [ ] **Step 1: chatStore 加 toolCalls 和 toolResults 数据结构**

读取 `ui/src/stores/chat.ts`，找到 `messages` 和 `currentAssistantMsg` 的定义。在 store 中添加：

```typescript
// 在现有 interface 定义附近添加
export interface ToolLabel {
  name: string;
  input: Record<string, any>;
  isError?: boolean;
  resultPreview?: string;
}

// 在 store 内部 state 区域添加
const toolLabels = ref<ToolLabel[]>([]);
```

并在 `finalizeAssistantMessage` 中把 toolLabels 附加到 message 上然后清空：

```typescript
function finalizeAssistantMessage() {
  const content = currentAssistantMsg.value;
  if (content) {
    messages.value.push({
      role: 'assistant',
      content,
      toolLabels: [...toolLabels.value],
    } as any);
    currentAssistantMsg.value = '';
    toolLabels.value = [];
  }
}
```

在 `clear()` 中也清空 `toolLabels.value = []`。

暴露 `toolLabels` 和追加函数：

```typescript
function addToolCall(name: string, input: Record<string, any>) {
  toolLabels.value.push({ name, input });
}

function addToolResult(index: number, resultPreview: string, isError: boolean) {
  if (toolLabels.value[index]) {
    toolLabels.value[index].resultPreview = resultPreview;
    toolLabels.value[index].isError = isError;
  }
}

return {
  // ... existing
  toolLabels,
  addToolCall,
  addToolResult,
};
```

- [ ] **Step 2: App.vue 监听 tool_use / tool_result 事件**

读取 `ui/src/App.vue`，在 `onMounted` 内找到现有 WS 事件绑定区域，添加：

```typescript
// Tool call labels for chat
let _toolCallIndex = 0;
agentWs.on('tool_use', (d: any) => {
  chatStore.addToolCall(d.name, d.input || {});
});

agentWs.on('tool_result', (d: any) => {
  chatStore.addToolResult(_toolCallIndex, d.result?.slice(0, 30) || '', d.is_error);
  _toolCallIndex++;
});

// Reset on new request or done
agentWs.on('thinking', () => { _toolCallIndex = 0; });
agentWs.on('done', () => { _toolCallIndex = 0; });
```

- [ ] **Step 3: ChatView.vue 渲染 toolCall 标签**

读取 `ui/src/components/ChatView.vue`，在 bubble-content 下方添加 tool 标签渲染：

```html
<div v-if="msg.toolLabels && msg.toolLabels.length" class="tool-labels">
  <div v-for="(tl, ti) in msg.toolLabels" :key="'tl-' + ti" class="tool-label">
    <span class="tool-icon">{{ tl.resultPreview ? (tl.isError ? '✗' : '✓') : '🔧' }}</span>
    <span class="tool-name">{{ tl.name }}</span>
    <span v-if="tl.resultPreview" class="tool-result">{{ tl.resultPreview }}</span>
  </div>
</div>
```

注意：需要把 `msg` 的类型从 strict 放宽，或者将 `toolLabels` 加入 ChatMessage 接口。在 `<script>` 中的 import 旁添加：

```typescript
interface ChatMessage {
  role: string;
  content: string;
  toolLabels?: ToolLabel[];
}
```

并从 chat store import `ToolLabel` 类型。

CSS：

```css
.tool-labels { margin-top: 4px; }
.tool-label {
  display: flex; align-items: center; gap: 4px;
  font-size: 13px; color: #64748B; padding: 2px 0;
}
.tool-icon { font-size: 12px; }
.tool-name { font-weight: 600; color: #475569; }
.tool-result {
  color: #94A3B8; max-width: 200px; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
}
```

- [ ] **Step 4: ChatView.vue 处理流式 assistant bubble**

当前 `currentAssistantMsg` 的 bubble 也需要 toolLabels 渲染。在流式 bubble 中（模板里第二个 `.bubble-row.assistant`），同样加上 tool-labels div，但使用 `chatStore.toolLabels`（ref 值）。

- [ ] **Step 5: 前端编译验证**

```bash
cd ui && npx vue-tsc --noEmit 2>&1 | head -20
```

修复类型错误。

- [ ] **Step 6: Commit**

```bash
git add ui/src/stores/chat.ts ui/src/components/ChatView.vue ui/src/App.vue
git commit -m "feat: add tool call/result labels in chat view"
```

---

### Task 2: 输入栏 Compacting 状态提示 + 跨 Agent 消息

**参考 Flet:** `flet_ui/app.py` `_on_enqueued`, `_on_subagent_done`; `flet_ui/input_bar.py` `set_compacting()`

**Files:**
- Modify: `ui/src/stores/agent.ts`
- Modify: `ui/src/components/InputBar.vue`
- Modify: `ui/src/App.vue`
- Modify: `ui/src/stores/chat.ts`

- [ ] **Step 1: agentStore 加 compacting 字段**

读取 `ui/src/stores/agent.ts`，在 store 中添加：

```typescript
const compacting = ref(false);

// 暴露
return {
  // ... existing
  compacting,
};
```

- [ ] **Step 2: App.vue 驱动 compacting 状态**

在 `ui/src/App.vue` 的 `onMounted` 中添加：

```typescript
agentWs.on('compact_call', () => { agentStore.compacting = true; });
agentWs.on('compact', () => { agentStore.compacting = false; });
agentWs.on('compact_done', () => { agentStore.compacting = false; });
```

- [ ] **Step 3: InputBar.vue 禁用 compacting 时输入**

读取 `ui/src/components/InputBar.vue`，找到 textarea 和 send 按钮。添加 `compacting` 绑定：

在 template 中给 textarea 和 button 加：
```html
:disabled="agentStore.busy || agentStore.compacting"
:placeholder="agentStore.compacting ? 'Compacting...' : '输入消息... (Ctrl+Enter 发送)'"
```

script 中 import `useAgentStore`（如果还没导入的话）。

- [ ] **Step 4: App.vue 处理 enqueued 和 subagent_done 消息**

在 App.vue 的 onMounted 中添加：

```typescript
agentWs.on('enqueued', (d: any) => {
  chatStore.messages.push({
    role: 'assistant',
    content: `**[Msg from ${d.from_name}]**\n${d.message?.slice(0, 200) || ''}`,
  } as any);
});

agentWs.on('subagent_done', (d: any) => {
  const icon = d.status === 'completed' ? '✓' : '✗';
  chatStore.messages.push({
    role: 'assistant',
    content: `**[Agent] ${d.agent_id} ${icon}**`,
  } as any);
  agentWs.send({ type: 'get_status' });
});
```

- [ ] **Step 5: 编译验证 + Commit**

```bash
cd ui && npx vue-tsc --noEmit
git add ui/src/stores/agent.ts ui/src/components/InputBar.vue ui/src/App.vue ui/src/stores/chat.ts
git commit -m "feat: compacting input disable + inter-agent chat notifications"
```

---

### Task 3: 配置面板 Provider 下拉 + 高级设置 + 添加/删除

**参考 Flet:** `flet_ui/config_dialog.py` 全文件

**Files:**
- Modify: `ui/src/components/ConfigDialog.vue`
- Modify: `ui/src/App.vue`（传更多数据给 ConfigDialog）

- [ ] **Step 1: ConfigDialog 加 provider 下拉和高级字段**

读取 `ui/src/components/ConfigDialog.vue`，完全重写表单部分。新表单结构：

```html
<template>
  <Teleport to="body">
    <div class="config-overlay" @click.self="$emit('close')">
      <div class="config-dialog">
        <div class="config-header">
          <span>配置</span>
          <button @click="$emit('close')">&times;</button>
        </div>
        <div class="config-body">
          <!-- Provider 下拉 -->
          <label>Provider</label>
          <select v-model="form.provider" @change="onProviderChange">
            <option v-for="p in providers" :key="p" :value="p">{{ p }}</option>
          </select>

          <!-- API Key -->
          <label>API Key</label>
          <input v-model="form.api_key" type="password" />

          <!-- Base URL -->
          <label>Base URL</label>
          <input v-model="form.base_url" />

          <!-- Model -->
          <label>Model</label>
          <input v-model="form.model" />

          <!-- Context Window -->
          <label>Context Window (tokens)</label>
          <input v-model.number="form.context_window" type="number" />

          <!-- Compact Threshold -->
          <label>Compact Threshold</label>
          <input v-model.number="form.compact_threshold" type="number" step="0.1" min="0.1" max="1.0" />

          <!-- Reserved Output -->
          <label>Reserved Output (tokens)</label>
          <input v-model.number="form.reserved_output" type="number" />

          <!-- Add Custom Provider -->
          <div class="add-provider">
            <input v-model="newProviderName" placeholder="新 provider 名称" />
            <select v-model="newProviderType">
              <option value="openai">OpenAI 兼容</option>
              <option value="anthropic">Anthropic 兼容</option>
            </select>
            <button @click="addProvider">添加</button>
          </div>

          <!-- Delete Provider -->
          <div v-if="providers.length > 0">
            <button @click="deleteProvider" class="btn-delete">删除当前 Provider</button>
          </div>
        </div>
        <div class="config-footer">
          <button @click="save">保存</button>
          <button @click="$emit('close')">取消</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
```

- [ ] **Step 2: ConfigDialog script 逻辑**

```typescript
<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { agentWs } from '../services/agentWs';

defineEmits(['close']);

const providers = ref<string[]>(['anthropic', 'openai', 'glm', 'deepseek']);
const form = ref({
  provider: 'anthropic',
  api_key: '',
  base_url: '',
  model: '',
  context_window: 128000,
  compact_threshold: 0.7,
  reserved_output: 4096,
});

const newProviderName = ref('');
const newProviderType = ref('openai');

// 从后端 status 获取当前配置
onMounted(() => {
  agentWs.send({ type: 'get_config' });
  // 简化处理：假设后端回复 config 事件
});

agentWs.on('config', (d: any) => {
  form.value = { ...form.value, ...d };
  if (d.providers) providers.value = d.providers;
});

function onProviderChange() {
  // 切换 provider 时自动填充字段
  agentWs.send({ type: 'get_config', provider: form.value.provider });
}

function addProvider() {
  const name = newProviderName.value.trim();
  if (name && !providers.value.includes(name)) {
    providers.value.push(name);
    newProviderName.value = '';
  }
}

function deleteProvider() {
  if (confirm(`确定删除 "${form.value.provider}"？`)) {
    providers.value = providers.value.filter(p => p !== form.value.provider);
    form.value.provider = providers.value[0] || '';
  }
}

function save() {
  agentWs.send({ type: 'reconfigure', config: form.value });
  emit('close');
}
</script>
```

添加基本样式（略，参考现有 ConfigDialog 样式，加 select/input 样式即可）。

- [ ] **Step 3: 编译验证 + Commit**

```bash
cd ui && npx vue-tsc --noEmit
git add ui/src/components/ConfigDialog.vue
git commit -m "feat: config dialog with provider dropdown, advanced settings, add/delete provider"
```

---

### Task 4: MCP 面板 Server 状态 + 停止/重启按钮

**参考 Flet:** `flet_ui/mcp_dialog.py` 全文件

**Files:**
- Modify: `ui/src/components/McpDialog.vue`
- Modify: `agentcore/ws_server.py`（加 mcp_stop / mcp_restart 消息）

- [ ] **Step 1: 后端加 mcp_stop / mcp_restart WS 消息**

读取 `agentcore/ws_server.py`，找到 `msg_type` 处理区（约 616 行），在 `compact` handler 附近添加：

```python
elif msg_type == "mcp_stop":
    server_name = msg.get("server_name", "")
    controller = manager.get_active().controller
    if controller.mcp_manager:
        await controller.mcp_manager.stop_server(server_name)
        await _send_mcp_info(websocket, controller)

elif msg_type == "mcp_restart":
    server_name = msg.get("server_name", "")
    controller = manager.get_active().controller
    if controller.mcp_manager:
        await controller.mcp_manager.restart_server(server_name)
        await _send_mcp_info(websocket, controller)
```

添加 `_send_mcp_info` 辅助函数（在 `_send_agent_list` 附近）：

```python
async def _send_mcp_info(ws, controller):
    info = controller.get_mcp_info()
    await ws.send(json.dumps({"type": "mcp_info", "mcp": info}, ensure_ascii=False))
```

- [ ] **Step 2: McpDialog.vue 重写为结构化列表**

读取并重写 `ui/src/components/McpDialog.vue`：

```html
<template>
  <Teleport to="body">
    <div class="mcp-overlay" @click.self="$emit('close')">
      <div class="mcp-dialog">
        <div class="mcp-header">
          <span>MCP 管理</span>
          <button @click="refresh">刷新</button>
          <button @click="$emit('close')">&times;</button>
        </div>
        <div class="mcp-body">
          <div v-if="!servers.length" class="mcp-empty">无 MCP 服务器</div>
          <div v-for="s in servers" :key="s.name" class="mcp-server">
            <div class="server-header">
              <span :class="'status-dot ' + s.status"></span>
              <span class="server-name">{{ s.name }}</span>
              <div class="server-actions">
                <button @click="stopServer(s.name)" :disabled="s.status !== 'connected'">停止</button>
                <button @click="restartServer(s.name)">重启</button>
              </div>
            </div>
            <details>
              <summary>工具 ({{ s.tool_count }})</summary>
              <div v-for="t in s.tools" :key="t.name" class="tool-item">
                <span class="tool-name">{{ t.name }}</span>
                <span class="tool-desc" v-if="t.description">{{ t.description }}</span>
              </div>
            </details>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
```

```typescript
<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { agentWs } from '../services/agentWs';

defineEmits(['close']);

interface McpServer {
  name: string;
  status: string;
  tool_count: number;
  tools: { name: string; description?: string }[];
}

const servers = ref<McpServer[]>([]);

onMounted(() => {
  agentWs.on('mcp_info', (d: any) => {
    if (d.mcp) {
      servers.value = d.mcp.servers || [];
    }
  });
  agentWs.on('status', (d: any) => {
    if (d.mcp) {
      servers.value = d.mcp.servers || [];
    }
  });
  agentWs.send({ type: 'get_status' });
});

function stopServer(name: string) { agentWs.send({ type: 'mcp_stop', server_name: name }); }
function restartServer(name: string) { agentWs.send({ type: 'mcp_restart', server_name: name }); }
function refresh() { agentWs.send({ type: 'get_status' }); }
</script>
```

CSS 加 status-dot 颜色、server 卡片样式等。

- [ ] **Step 3: 验证 + Commit**

```bash
cd ui && npx vue-tsc --noEmit
cd .. && python -c "from agentcore.ws_server import run_ws_server; print('backend OK')"
git add ui/src/components/McpDialog.vue agentcore/ws_server.py
git commit -m "feat: MCP server status badges, stop/restart, expandable tool list"
```

---

### Task 5: 侧边栏折叠动画 + 状态颜色对齐

**参考 Flet:** `flet_ui/agent_sidebar.py` 全文件

**Files:**
- Modify: `ui/src/components/AgentSidebar.vue`

- [ ] **Step 1: AgentSidebar 重写模板，加折叠状态**

```html
<template>
  <div :class="['agent-sidebar', { collapsed }]">
    <!-- 折叠切换按钮 -->
    <button class="collapse-toggle" @click="collapsed = !collapsed">
      {{ collapsed ? '▶' : '◀' }}
    </button>

    <!-- 展开内容 -->
    <div v-if="!collapsed" class="sidebar-content">
      <div class="sidebar-title">Agents</div>
      <div
        v-for="agent in agentStore.agentList"
        :key="agent.id"
        :class="['agent-item', { active: agent.active }]"
        @click="switchAgent(agent.id)"
      >
        <span :class="'dot ' + agent.status"></span>
        <div class="agent-info">
          <span class="agent-name">{{ agent.name }}</span>
          <span class="agent-subtitle">{{ agent.id === 'master' ? '主 Agent' : agent.status }}</span>
        </div>
        <span v-if="agent.est_tokens" class="agent-tokens">~{{ agent.est_tokens }}</span>
        <button v-if="agent.id !== 'master'" class="kill-btn" @click.stop="killAgent(agent.id)">&times;</button>
      </div>

      <!-- Spawn -->
      <div v-if="showSpawn" class="spawn-form">
        <input v-model="spawnName" placeholder="Agent 名称" />
        <input v-model="spawnPrompt" placeholder="初始 prompt" />
        <button @click="doSpawn">创建</button>
        <button @click="showSpawn = false">取消</button>
      </div>
      <button v-else class="add-btn" @click="showSpawn = true">+ 新 Agent</button>
    </div>
  </div>
</template>
```

- [ ] **Step 2: Script 逻辑**

```typescript
<script setup lang="ts">
import { ref } from 'vue';
import { useAgentStore } from '../stores/agent';
import { agentWs } from '../services/agentWs';

const agentStore = useAgentStore();
const collapsed = ref(false);
const showSpawn = ref(false);
const spawnName = ref('');
const spawnPrompt = ref('');

function switchAgent(id: string) {
  agentWs.send({ type: 'switch_agent', agent_id: id });
}

function killAgent(id: string) {
  agentWs.send({ type: 'kill_agent', agent_id: id });
}

function doSpawn() {
  if (spawnName.value.trim()) {
    agentWs.send({
      type: 'spawn_agent',
      agent_name: spawnName.value.trim(),
      prompt: spawnPrompt.value.trim(),
    });
    spawnName.value = '';
    spawnPrompt.value = '';
    showSpawn.value = false;
  }
}
</script>
```

- [ ] **Step 3: CSS 折叠动画 + 状态颜色**

```css
.agent-sidebar {
  width: 160px; border-right: 1px solid #F1F3F6; background: #FAFBFC;
  display: flex; flex-direction: column; padding: 8px;
  transition: width 0.2s ease;
}
.agent-sidebar.collapsed { width: 36px; padding: 8px 4px; }
.collapse-toggle {
  background: none; border: none; cursor: pointer; font-size: 12px;
  padding: 2px; align-self: flex-end;
}
.sidebar-content { flex: 1; overflow-y: auto; }
.sidebar-title { font-size: 14px; font-weight: 600; margin-bottom: 8px; color: #475569; }
.agent-item {
  display: flex; align-items: center; gap: 6px; padding: 6px; border-radius: 6px;
  cursor: pointer; font-size: 13px;
}
.agent-item:hover { background: #EEF0F4; }
.agent-item.active { background: #E0E7FF; }
.agent-info { flex: 1; min-width: 0; }
.agent-name { font-weight: 600; display: block; }
.agent-subtitle { font-size: 11px; color: #94A3B8; }
.agent-tokens { font-size: 11px; color: #94A3B8; }
.kill-btn { background: none; border: none; color: #EF4444; cursor: pointer; font-size: 14px; }
.add-btn { width: 100%; padding: 6px; border: 1px dashed #DDE0E5; border-radius: 6px; cursor: pointer; font-size: 13px; }
.spawn-form { display: flex; flex-direction: column; gap: 4px; margin-top: 8px; }
.spawn-form input { padding: 4px 6px; border: 1px solid #E2E6EC; border-radius: 4px; font-size: 13px; }
.spawn-form button { padding: 4px 8px; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; }

/* Status dot colors — aligned with Flet */
.dot {
  width: 8px; height: 8px; border-radius: 4px; flex-shrink: 0;
}
.dot.running { background: #3B82F6; }
.dot.completed { background: #22C55E; }
.dot.failed { background: #EF4444; }
.dot.killed { background: #94A3B8; }
.dot.pending, .dot.idle { background: #F59E0B; }
```

- [ ] **Step 4: 编译验证 + Commit**

```bash
cd ui && npx vue-tsc --noEmit
git add ui/src/components/AgentSidebar.vue
git commit -m "feat: collapsible sidebar with animation, correct status colors, token display"
```

---

### Task 6: 调试面板折叠模式 + 保留 System + Compact 状态

**参考 Flet:** `flet_ui/debug_drawer.py` `MIN_WIDTH`, collapsed mode

**Files:**
- Modify: `ui/src/components/DebugDrawer.vue`
- Modify: `ui/src/stores/debug.ts`
- Modify: `ui/src/App.vue`

- [ ] **Step 1: debugStore.clear() 保留 System 条目**

读取 `ui/src/stores/debug.ts`，修改 `clear` 函数：

```typescript
function clear() {
  // Preserve System entries (no group_key) — matches Flet behavior
  entries.value = entries.value.filter(e => !e.groupKey);
}
```

- [ ] **Step 2: Compact 按钮绑定后端 compact 状态**

在 `ui/src/App.vue` 的 `onMounted` 中，Compact 相关事件已处理（Task 2）。现在把 `compacting` 状态传给 DebugDrawer。

读取 `ui/src/components/DebugDrawer.vue`，Compact 按钮应绑定 `debugStore.compacting`：

```html
<button class="btn-compact" @click="onCompact" :disabled="debugStore.compacting">
  {{ debugStore.compacting ? 'Compacting...' : 'Compact' }}
</button>
```

并在 `onCompact` 中设置状态：

```typescript
function onCompact() {
  debugStore.setCompacting(true);
  agentWs.send({ type: 'compact' });
}
```

App.vue 中 compact 完成时重置：

```typescript
agentWs.on('compact', () => { debugStore.setCompacting(false); });
```

- [ ] **Step 3: 调试面板折叠模式**

给 DebugDrawer 加 collapsed 属性。修改 root div：

```html
<div :class="['debug-drawer', { collapsed }]" :style="collapsed ? {} : { width: drawerWidth + 'px', minWidth: drawerWidth + 'px' }">
  <!-- 折叠切换按钮 -->
  <button class="collapse-toggle" @click="collapsed = !collapsed">
    {{ collapsed ? '◀' : '▶' }}
  </button>

  <template v-if="!collapsed">
    <!-- 现有所有内容 -->
  </template>

  <template v-else>
    <div class="collapsed-label">调<br>试</div>
  </template>
</div>
```

CSS：

```css
.debug-drawer.collapsed {
  width: 36px !important; min-width: 36px !important; padding: 4px;
}
.collapsed-label {
  writing-mode: vertical-lr; font-size: 14px; color: #64748B;
  text-align: center; height: 100%; display: flex; align-items: center;
  justify-content: center;
}
.collapse-toggle {
  position: absolute; left: 4px; top: 8px;
  background: none; border: none; cursor: pointer; font-size: 10px;
  padding: 1px 3px; z-index: 11;
}
```

- [ ] **Step 4: 编译验证 + Commit**

```bash
cd ui && npx vue-tsc --noEmit
git add ui/src/components/DebugDrawer.vue ui/src/stores/debug.ts ui/src/App.vue
git commit -m "feat: debug drawer collapse mode, preserve system entries on clear, compact state binding"
```

---

### Task 7: 技能面板结构化卡片

**参考 Flet:** `flet_ui/skill_dialog.py` 全文件

**Files:**
- Modify: `ui/src/components/SkillDialog.vue`

- [ ] **Step 1: 解析 skills 字符串为卡片**

读取 `ui/src/components/SkillDialog.vue`，完全重写：

```html
<template>
  <Teleport to="body">
    <div class="skill-overlay" @click.self="$emit('close')">
      <div class="skill-dialog">
        <div class="skill-header">
          <span>技能管理 ({{ skills.length }})</span>
          <button @click="$emit('close')">&times;</button>
        </div>
        <div class="skill-body">
          <div v-for="(sk, i) in skills" :key="i" class="skill-card">
            <div class="skill-name">{{ sk.name }}</div>
            <div class="skill-desc" v-if="sk.description">{{ sk.description }}</div>
          </div>
          <div v-if="!skills.length" class="skill-empty">暂无可用技能</div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
```

```typescript
<script setup lang="ts">
import { computed } from 'vue';
import { useAgentStore } from '../stores/agent';

defineEmits(['close']);
const agentStore = useAgentStore();

interface SkillItem {
  name: string;
  description: string;
}

const skills = computed<SkillItem[]>(() => {
  const text = agentStore.skills || '';
  if (!text.trim()) return [];

  // Parse: skills are separated by blank lines or lines starting with name:
  // Simple heuristic: split by double newline, first line = name, rest = description
  return text.split('\n\n')
    .filter(block => block.trim())
    .map(block => {
      const lines = block.trim().split('\n');
      // Try name: description format first
      const firstLine = lines[0];
      const colonIdx = firstLine.indexOf(':');
      if (colonIdx > 0) {
        return {
          name: firstLine.slice(0, colonIdx).trim(),
          description: firstLine.slice(colonIdx + 1).trim() + (lines.length > 1 ? '\n' + lines.slice(1).join('\n') : ''),
        };
      }
      return { name: firstLine, description: lines.slice(1).join('\n') };
    });
});
</script>
```

CSS：

```css
.skill-overlay { /* same as other overlays */ }
.skill-dialog { /* same dialog pattern */ }
.skill-card {
  padding: 8px 12px; border: 1px solid #E2E6EC; border-radius: 8px;
  margin-bottom: 6px;
}
.skill-name { font-weight: 600; font-size: 14px; color: #1E1B3A; }
.skill-desc { font-size: 13px; color: #64748B; margin-top: 2px; white-space: pre-wrap; }
.skill-empty { text-align: center; color: #94A3B8; font-size: 14px; padding: 16px; }
```

- [ ] **Step 2: 编译验证 + Commit**

```bash
cd ui && npx vue-tsc --noEmit
git add ui/src/components/SkillDialog.vue
git commit -m "feat: structured skill cards in skill dialog"
```

---

### Task 8: App 级启动恢复 + `/compact` 命令

**参考 Flet:** `flet_ui/app.py` `_manual_compact` + startup error handling

**Files:**
- Modify: `ui/src/App.vue`

- [ ] **Step 1: `/compact` 命令拦截**

在 App.vue 中找到发送消息的位置。InputBar 发出的事件需要被 App 或 InputBar 本身拦截。在 InputBar 的 send 函数中添加：

读取 `ui/src/components/InputBar.vue`，找到 send 函数：

```typescript
function send() {
  const text = inputText.value.trim();
  if (!text) return;

  // Intercept /compact command
  if (text === '/compact') {
    agentWs.send({ type: 'compact' });
    inputText.value = '';
    return;
  }

  agentWs.send({ type: 'send_message', text });
  chatStore.startUserMessage(text);
  inputText.value = '';
}
```

- [ ] **Step 2: 启动恢复——WS 错误时显示提示**

在 App.vue 的 onMounted 中，处理 WS 错误：

```typescript
agentWs.on('error', (d: any) => {
  if (d.message && d.message.includes('init')) {
    chatStore.messages.push({
      role: 'assistant',
      content: `**初始化失败**: ${d.message}\n\n请检查配置后重试。`,
    } as any);
  }
});

agentWs.on('connected', () => {
  agentWs.send({ type: 'get_status' });
});
```

- [ ] **Step 3: 编译验证 + Commit**

```bash
cd ui && npx vue-tsc --noEmit
git add ui/src/components/InputBar.vue ui/src/App.vue
git commit -m "feat: /compact command + init error recovery message"
```

---

## 验证

启动后端和前端，逐项验证：

1. 发消息触发 tool call → 聊天显示 `[Tool] Read ✓` 等内联标签
2. 点 Compact → 输入栏显示 "Compacting..."，不可输入
3. 另一个 Agent 发来消息 → 聊天显示 `[Msg from X]`
4. Subagent 完成 → 聊天显示 `[Agent] X ✓`
5. 配置面板 → Provider 是下拉框，可切换/添加/删除
6. MCP 面板 → 每个 Server 有状态点 + 停止/重启按钮
7. 侧边栏 → 可折叠，动画流畅，状态颜色正确
8. 调试面板 → 可折叠到竖排"调试"，Clear 保留 System 行
9. 技能面板 → 每项技能显示为卡片
10. 输入 `/compact` → 触发压缩
