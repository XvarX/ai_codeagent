<template>
  <div class="app-layout">
    <header class="app-header">
      <button class="sidebar-toggle" @click="showSidebar = !showSidebar">&#9776;</button>
      <span class="app-title">{{ agentStore.provider }} / {{ agentStore.model }}</span>
      <div class="header-actions">
        <button @click="showSkill = true" title="Skills">&#9889;</button>
        <button @click="showMcp = true" title="MCP">&#128268;</button>
        <button @click="showConfig = true" title="Config">&#9881;</button>
        <button @click="onClear" title="Clear">&#128465;</button>
        <button @click="debugStore.open = !debugStore.open" title="Debug">&#128027;</button>
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

onMounted(() => {
  agentWs.on('connected', () => agentWs.send({ type: 'get_status' }));
  agentWs.on('thinking', () => chatStore.startThinking());
  agentWs.on('text_delta', (d: { token: string }) => chatStore.appendToken(d.token));
  agentWs.on('done', () => chatStore.finalizeAssistantMessage());
  agentWs.on('error', (d: { message: string }) => debugStore.addEvent('[Error]', d.message, '#EF4444'));
  agentWs.on('status', (d: any) => agentStore.setFromStatus(d));
  agentWs.on('tool_use', (d: { name: string; [k: string]: any }) => debugStore.addEvent('[Tool]', `${d.name}`, '#6366F1', d));
  agentWs.on('tool_result', (d: { name: string; is_error: boolean; [k: string]: any }) => debugStore.addEvent('[Result]', `${d.name} ${d.is_error ? '✗' : '✓'}`, d.is_error ? '#EF4444' : '#22C55E', d));
  agentWs.on('request', (d: { model: string; est_tokens: number }) => debugStore.addEvent('[Request]', `${d.model} tokens≈${d.est_tokens}`, '#6366F1', d));
  agentWs.on('compact_call', (d: { pre_tokens: number }) => debugStore.addEvent('[Compact]', `pre=${d.pre_tokens}`, '#F59E0B'));
  agentWs.on('compact', (d: { pre_tokens: number; post_tokens: number }) => debugStore.addEvent('[Compact]', `${d.pre_tokens}→${d.post_tokens}`, '#F59E0B'));
  agentWs.on('snip', (d: { groups_removed: number }) => debugStore.addEvent('[Snip]', `-${d.groups_removed} groups`, '#F59E0B'));
  agentWs.on('send_message', () => agentStore.setBusy(true));
  agentWs.on('done', () => agentStore.setBusy(false));
  agentWs.on('error', () => agentStore.setBusy(false));
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
