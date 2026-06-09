<template>
  <div class="flex flex-col h-screen bg-surface-0">
    <header class="flex items-center h-10 px-3 border-b border-border-default bg-surface-1 gap-2">
      <button class="bg-transparent border-none text-lg cursor-pointer p-1 text-text-primary" @click="showSidebar = !showSidebar">&#9776;</button>
      <button class="bg-transparent border border-border-default rounded-md px-[10px] py-1 cursor-pointer text-sm text-accent hover:bg-surface-2" @click="showProjectPicker = true">
        {{ sessionStore.currentProjectName || '选择项目' }}
      </button>
      <span class="text-sm text-text-secondary flex-1">{{ agentStore.provider }} / {{ agentStore.model }}</span>
      <div class="flex gap-1">
        <button class="bg-transparent border border-border-default rounded-md px-2 py-1 cursor-pointer text-sm text-text-secondary hover:bg-surface-2" @click="showSkill = true">技能</button>
        <button class="bg-transparent border border-border-default rounded-md px-2 py-1 cursor-pointer text-sm text-text-secondary hover:bg-surface-2" @click="showMcp = true">MCP</button>
        <button class="bg-transparent border border-border-default rounded-md px-2 py-1 cursor-pointer text-sm text-text-secondary hover:bg-surface-2" @click="showConfig = true">配置</button>
        <button class="bg-transparent border border-border-default rounded-md px-2 py-1 cursor-pointer text-sm text-text-secondary hover:bg-surface-2" @click="onClear">清理</button>
        <button class="bg-transparent border border-border-default rounded-md px-2 py-1 cursor-pointer text-sm text-text-secondary hover:bg-surface-2" @click="debugStore.open = !debugStore.open">调试</button>
      </div>
    </header>
    <div class="flex flex-1 overflow-hidden">
      <div v-if="showSidebar" class="flex flex-col border-r border-border-default bg-surface-1 min-w-[200px] max-w-[260px]">
        <SessionList @showMore="showAllSessions = true" />
      </div>
      <div class="flex-1 flex flex-col overflow-hidden">
        <ChatView class="flex-1" />
        <AgentPanel />
      </div>
      <DebugDrawer v-if="debugStore.open" />
    </div>
    <InputBar />
    <ConfigDialog v-if="showConfig" @close="showConfig = false" />
    <McpDialog v-if="showMcp" @close="showMcp = false" />
    <SkillDialog v-if="showSkill" @close="showSkill = false" />
    <ProjectPicker v-if="showProjectPicker" @close="showProjectPicker = false" />
    <AllSessionsDialog v-if="showAllSessions" @close="showAllSessions = false" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { useChatStore } from './stores/chat';
import { useAgentStore } from './stores/agent';
import { useDebugStore } from './stores/debug';
import { useSessionStore } from './stores/session';
import { agentWs } from './services/agentWs';
import ProjectPicker from './components/ProjectPicker.vue';
import SessionList from './components/SessionList.vue';
import AllSessionsDialog from './components/AllSessionsDialog.vue';
import ChatView from './components/ChatView.vue';
import InputBar from './components/InputBar.vue';
import DebugDrawer from './components/DebugDrawer.vue';
import AgentPanel from './components/AgentPanel.vue';
import ConfigDialog from './components/ConfigDialog.vue';
import McpDialog from './components/McpDialog.vue';
import SkillDialog from './components/SkillDialog.vue';

const chatStore = useChatStore();
const agentStore = useAgentStore();
const debugStore = useDebugStore();
const sessionStore = useSessionStore();

const showSidebar = ref(false);
const showProjectPicker = ref(false);
const showAllSessions = ref(false);
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
    agentStore.setBusy(false);
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
  agentWs.on('connected', () => {
    agentWs.send({ type: 'get_status' });
    sessionStore.listProjects();
  });
  agentWs.on('status', (d: any) => agentStore.setFromStatus(d));
  agentWs.on('mcp_info', (d: any) => {
    if (d.mcp) agentStore.mcpInfo = d.mcp;
  });
  agentWs.on('error', () => agentStore.setBusy(false));

  // Session events
  agentWs.on('projects', (d: any) => sessionStore.setProjects(d.projects, d.default_cwd));
  agentWs.on('project_opened', (d: any) => {
    sessionStore.setProjectOpened(d.path, d.sessions);
    chatStore.clear();
    debugStore.clear();
  });
  agentWs.on('session_created', (d: any) => {
    sessionStore.setSessionCreated(d.session_id, d.title);
    chatStore.clear();
    if (d.debug_entries) {
      debugStore.loadEvents(d.debug_entries);
    } else {
      debugStore.clear();
    }
    debugStore.updateContextUsage(0);
  });
  agentWs.on('session_loaded', (d: any) => {
    sessionStore.setCurrentSession(d.session_id);
    chatStore.loadMessages(
      (d.messages || []).map((m: any) => ({ role: m.role, content: m.content }))
    );
    if (d.debug_entries) {
      debugStore.loadEvents(d.debug_entries);
    } else {
      debugStore.clear();
    }
    chatStore.updateUsage(d.est_tokens || 0);
    debugStore.updateContextUsage(d.est_tokens || 0);
  });

  // Background session status updates
  agentWs.on('session_status', (d: any) => {
    sessionStore.setSessionStatus(d.session_id, d.status);
  });

  // Active session switched (from switch_session message)
  agentWs.on('active_session_switched', (d: any) => {
    sessionStore.setCurrentSession(d.session_id);
    chatStore.loadMessages(
      (d.messages || []).map((m: any) => ({ role: m.role, content: m.content }))
    );
    if (d.debug_entries) {
      debugStore.loadEvents(d.debug_entries);
    } else {
      debugStore.clear();
    }
    chatStore.updateUsage(d.est_tokens || 0);
    debugStore.updateContextUsage(d.est_tokens || 0);
  });

  // Session destroyed (close)
  agentWs.on('session_destroyed', (d: any) => {
    sessionStore.removeSession(d.session_id);
    chatStore.clear();
    debugStore.clear();
  });

  // Session deleted (permanent)
  agentWs.on('session_deleted', (d: any) => {
    sessionStore.removeSession(d.session_id);
    if (sessionStore.currentSessionId === d.session_id) {
      chatStore.clear();
      debugStore.clear();
    }
  });

  // Project deleted (permanent)
  agentWs.on('project_deleted', (_d: any) => {
    // Refresh projects list
    sessionStore.listProjects();
  });

  // Agent switching — full state reload
  agentWs.on('agent_switched', (d: any) => {
    agentStore.setActiveAgent(d.agent_id);
    chatStore.loadMessages(d.messages || []);
    debugStore.loadEvents(d.debug_events || []);
    chatStore.updateUsage(d.est_tokens || 0);
    debugStore.updateContextUsage(d.est_tokens || 0);
  });

  // Compacting state
  agentWs.on('compact_call', () => { agentStore.compacting = true; });
  agentWs.on('compact', () => { agentStore.compacting = false; });
  agentWs.on('compact_done', () => { agentStore.compacting = false; });

  // Agent lifecycle — refresh on spawn / completion
  agentWs.on('subagent_done', () => { agentWs.send({ type: 'get_status' }); });
  agentWs.on('agent_spawned', () => { agentWs.send({ type: 'get_status' }); });

  // Agent list updates
  agentWs.on('agent_list', (d: any) => {
    agentStore.setAgentList(d.agents);
  });

  agentWs.connect();
});

onUnmounted(() => agentWs.disconnect());
</script>
