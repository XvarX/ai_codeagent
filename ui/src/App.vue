<template>
  <div class="app-layout">
    <header class="app-header">
      <button class="sidebar-toggle" @click="showSidebar = !showSidebar">&#9776;</button>
      <span class="app-title">{{ agentStore.provider }} / {{ agentStore.model }}</span>
      <div class="header-actions">
        <button @click="showSkill = true">技能</button>
        <button @click="showMcp = true">MCP</button>
        <button @click="showConfig = true">配置</button>
        <button @click="onClear">清理</button>
        <button @click="debugStore.open = !debugStore.open">调试</button>
      </div>
    </header>
    <div class="app-body">
      <AgentSidebar v-if="showSidebar" />
      <ChatView class="chat-main" />
      <DebugDrawer v-if="debugStore.open" />
    </div>
    <InputBar />
    <ConfigDialog v-if="showConfig" @close="showConfig = false" />
    <McpDialog v-if="showMcp" @close="showMcp = false" />
    <SkillDialog v-if="showSkill" @close="showSkill = false" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { useChatStore } from './stores/chat';
import { useAgentStore } from './stores/agent';
import { useDebugStore } from './stores/debug';
import { agentWs } from './services/agentWs';
import ChatView from './components/ChatView.vue';
import InputBar from './components/InputBar.vue';
import DebugDrawer from './components/DebugDrawer.vue';
import AgentSidebar from './components/AgentSidebar.vue';
import ConfigDialog from './components/ConfigDialog.vue';
import McpDialog from './components/McpDialog.vue';
import SkillDialog from './components/SkillDialog.vue';

const chatStore = useChatStore();
const agentStore = useAgentStore();
const debugStore = useDebugStore();

const showSidebar = ref(false);
const showConfig = ref(false);
const showMcp = ref(false);
const showSkill = ref(false);

function onClear() {
  chatStore.clear();
  agentWs.send({ type: 'clear_history' });
}

// Tool call labels for chat stream
let _toolCallIndex = 0;

onMounted(() => {
  // Chat streaming events
  agentWs.on('thinking', () => {
    chatStore.startThinking();
    _toolCallIndex = 0;
  });
  agentWs.on('text_delta', (d: { token: string; reasoning?: boolean }) => {
    if (!d.reasoning) chatStore.appendToken(d.token);
  });
  agentWs.on('done', () => {
    chatStore.finalizeAssistantMessage();
    _toolCallIndex = 0;
  });

  // Tool call labels for chat stream
  agentWs.on('tool_use', (d: any) => {
    chatStore.addToolCall(d.name, d.input || {});
  });
  agentWs.on('tool_result', (d: any) => {
    const preview = d.result ? d.result.slice(0, 30).replace(/\n/g, ' ') : '';
    chatStore.addToolResultPreview(_toolCallIndex, preview, d.is_error);
    _toolCallIndex++;
  });

  // Tool results — capture diff data for DiffViewer
  agentWs.on('tool_result', (d: any) => {
    if (d.diff) {
      chatStore.addDiff(d.diff.file_path, d.diff.old_content, d.diff.new_content);
    }
  });

  // Debug panel — all formatted events come via debug_event
  agentWs.on('debug_event', (d: any) => {
    debugStore.addEvent(d.prefix, d.message, d.color, d.data, d.group_key, d.group_idx);
  });

  // Compact/sync — full debug state refresh
  agentWs.on('debug_sync', (d: any) => {
    debugStore.syncEvents(d.entries);
  });

  // Context usage from backend
  agentWs.on('response_done', (d: any) => {
    const usage = d.raw?.usage || {};
    const total = usage.total_tokens || usage.totalTokens || 0;
    debugStore.updateContextUsage(total, 128000);
    chatStore.updateUsage(total);
  });
  agentWs.on('context_usage', (d: any) => {
    debugStore.updateContextUsage(d.total_tokens || 0, d.max_tokens || 128000);
    chatStore.updateUsage(d.total_tokens || 0);
  });

  // Agent state
  agentWs.on('connected', () => agentWs.send({ type: 'get_status' }));
  agentWs.on('status', (d: any) => agentStore.setFromStatus(d));
  agentWs.on('done', () => agentStore.setBusy(false));
  agentWs.on('error', () => agentStore.setBusy(false));

  // Agent switching — full state reload
  agentWs.on('agent_switched', (d: any) => {
    agentStore.setActiveAgent(d.agent_id);
    chatStore.loadMessages(d.messages || []);
    debugStore.loadEvents(d.debug_events || []);
    chatStore.updateUsage(d.est_tokens || 0);
  });

  // Compacting state
  agentWs.on('compact_call', () => { agentStore.compacting = true; });
  agentWs.on('compact', () => { agentStore.compacting = false; });
  agentWs.on('compact_done', () => { agentStore.compacting = false; });

  // Inter-agent messages in chat
  agentWs.on('enqueued', (d: any) => {
    chatStore.messages.push({ role: 'assistant', content: `**[Msg from ${d.from_name}]**\n${(d.message || '').slice(0, 200)}` } as any);
  });

  // Subagent completion + notifications in chat
  agentWs.on('subagent_done', (d: any) => {
    const icon = d.status === 'completed' ? '✓' : '✗';
    chatStore.messages.push({ role: 'assistant', content: `**[Agent] ${d.agent_id} ${icon}**` } as any);
    agentWs.send({ type: 'get_status' });
  });

  // Agent list updates
  agentWs.on('agent_list', (d: any) => {
    agentStore.setAgentList(d.agents);
  });

  // Agent spawned — refresh status
  agentWs.on('agent_spawned', () => {
    agentWs.send({ type: 'get_status' });
  });

  agentWs.connect();
});

onUnmounted(() => agentWs.disconnect());
</script>

<style>
/* Global styles */
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #1E1B3A; background: #FAFBFC; }
.app-layout { display: flex; flex-direction: column; height: 100vh; }
.app-header { display: flex; align-items: center; padding: 0 12px; height: 40px; border-bottom: 1px solid #F1F3F6; background: white; gap: 8px; }
.sidebar-toggle { background: none; border: none; font-size: 18px; cursor: pointer; padding: 4px; }
.app-title { font-size: 15px; color: #64748B; flex: 1; }
.header-actions { display: flex; gap: 4px; }
.header-actions button { background: none; border: 1px solid #E2E6EC; border-radius: 6px; padding: 4px 8px; cursor: pointer; font-size: 14px; }
.app-body { display: flex; flex: 1; overflow: hidden; }
.chat-main { flex: 1; }
</style>
