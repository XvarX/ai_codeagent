<template>
  <div class="agent-sidebar">
    <div class="sidebar-header"><h3>Agents</h3></div>
    <div class="agent-list">
      <div v-for="agent in agentStore.agents" :key="agent.id"
           :class="['agent-item', { active: agent.id === 'master' }]">
        <span class="agent-name">{{ agent.name }}</span>
        <span :class="['agent-status', agent.status]"></span>
      </div>
    </div>
    <div v-if="!agentStore.agents.length" class="agent-empty">
      No agents
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAgentStore } from '../stores/agent';
const agentStore = useAgentStore();
</script>

<style scoped>
.agent-sidebar {
  width: 160px; min-width: 160px;
  border-right: 1px solid #F1F3F6; background: #FAFBFC;
  padding: 12px; display: flex; flex-direction: column;
}
.sidebar-header h3 { font-size: 14px; color: #1E1B3A; margin-bottom: 8px; }
.agent-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 6px 8px; border-radius: 6px; cursor: pointer; font-size: 13px;
}
.agent-item:hover { background: #F1F3F6; }
.agent-item.active { background: #EBF5FF; }
.agent-status {
  width: 8px; height: 8px; border-radius: 4px;
  background: #94A3B8;
}
.agent-status.running { background: #22C55E; }
.agent-status.idle { background: #94A3B8; }
.agent-status.error { background: #EF4444; }
.agent-empty { color: #94A3B8; font-size: 13px; padding: 8px; }
</style>
