<template>
  <div :class="['agent-sidebar', { collapsed }]">
    <button class="toggle-btn" @click="collapsed = !collapsed" :title="collapsed ? 'Expand' : 'Collapse'">
      {{ collapsed ? '▶' : '◀' }}
    </button>

    <template v-if="!collapsed">
      <div class="sidebar-header">
        <h3>Agents</h3>
        <button class="btn-spawn" @click="showSpawn = true" title="Spawn">+</button>
      </div>
      <div class="agent-list">
        <div v-for="agent in agentStore.agents" :key="agent.id"
             :class="['agent-item', { active: agent.id === agentStore.activeAgentId }]"
             @click="switchTo(agent.id)">
          <div class="agent-info">
            <span class="agent-name">{{ agent.name }}</span>
            <div class="agent-meta">
              <span v-if="agent.id === 'master'" class="agent-subtitle">主 Agent</span>
              <span v-if="agent.est_tokens" class="agent-tokens">~{{ agent.est_tokens }}t</span>
            </div>
          </div>
          <div class="agent-right">
            <span class="agent-status" :style="{ backgroundColor: statusColor(agent.status) }"></span>
            <button v-if="agent.id !== 'master'" class="btn-kill" @click.stop="kill(agent.id)" title="Kill">&times;</button>
          </div>
        </div>
      </div>
      <div v-if="!agentStore.agents.length" class="agent-empty">No agents</div>

      <!-- Spawn dialog -->
      <div v-if="showSpawn" class="spawn-overlay" @click.self="showSpawn = false">
        <div class="spawn-dialog">
          <h4>Spawn Agent</h4>
          <input v-model="spawnName" placeholder="Agent name" class="spawn-input" />
          <textarea v-model="spawnPrompt" placeholder="Task prompt..." class="spawn-textarea" rows="3"></textarea>
          <div class="spawn-actions">
            <button class="btn-go" @click="spawn" :disabled="!spawnName.trim() || !spawnPrompt.trim()">Go</button>
            <button class="btn-cancel" @click="showSpawn = false">Cancel</button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useAgentStore } from '../stores/agent';
import { agentWs } from '../services/agentWs';

const agentStore = useAgentStore();
const collapsed = ref(false);
const showSpawn = ref(false);
const spawnName = ref('');
const spawnPrompt = ref('');

function statusColor(status: string): string {
  switch (status) {
    case 'running': return '#3B82F6';
    case 'completed': return '#22C55E';
    case 'failed':
    case 'error': return '#EF4444';
    case 'killed': return '#94A3B8';
    case 'pending':
    case 'idle':
    default: return '#F59E0B';
  }
}

function switchTo(id: string) {
  if (id !== agentStore.activeAgentId) {
    agentWs.send({ type: 'switch_agent', agent_id: id });
  }
}

function spawn() {
  agentWs.send({ type: 'spawn_agent', agent_name: spawnName.value.trim(), prompt: spawnPrompt.value.trim() });
  showSpawn.value = false;
  spawnName.value = '';
  spawnPrompt.value = '';
}

function kill(id: string) {
  agentWs.send({ type: 'kill_agent', agent_id: id });
}
</script>

<style scoped>
.agent-sidebar {
  width: 160px; min-width: 160px;
  border-right: 1px solid #F1F3F6; background: #FAFBFC;
  padding: 12px; display: flex; flex-direction: column;
  transition: width 0.2s ease, min-width 0.2s ease;
  overflow: hidden;
}
.agent-sidebar.collapsed {
  width: 36px; min-width: 36px;
  padding: 12px 0;
  align-items: center;
}

.toggle-btn {
  background: none; border: none; cursor: pointer;
  font-size: 12px; color: #94A3B8; padding: 4px;
  flex-shrink: 0;
  width: 20px; height: 20px; display: flex;
  align-items: center; justify-content: center;
  border-radius: 4px;
}
.toggle-btn:hover { background: #F1F3F6; color: #6366F1; }

.sidebar-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.sidebar-header h3 { font-size: 14px; color: #1E1B3A; }
.btn-spawn { width: 22px; height: 22px; border-radius: 5px; border: 1px solid #E2E6EC; background: white; cursor: pointer; font-size: 14px; color: #6366F1; flex-shrink: 0; }

.agent-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 6px 8px; border-radius: 6px; cursor: pointer; font-size: 13px;
}
.agent-item:hover { background: #F1F3F6; }
.agent-item.active { background: #EBF5FF; }

.agent-info { display: flex; flex-direction: column; min-width: 0; }
.agent-name { font-weight: 500; color: #1E1B3A; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.agent-meta { display: flex; align-items: center; gap: 6px; margin-top: 1px; }
.agent-subtitle { font-size: 11px; color: #94A3B8; }
.agent-tokens { font-size: 11px; color: #A5B4FC; }

.agent-right { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
.agent-status { width: 8px; height: 8px; border-radius: 4px; flex-shrink: 0; }

.btn-kill { background: none; border: none; color: #94A3B8; cursor: pointer; font-size: 14px; padding: 0 2px; }
.btn-kill:hover { color: #EF4444; }
.agent-empty { color: #94A3B8; font-size: 13px; padding: 8px; }

.spawn-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.2); display: flex; align-items: center; justify-content: center; z-index: 200; }
.spawn-dialog { background: white; border-radius: 10px; padding: 20px; min-width: 300px; box-shadow: 0 4px 20px rgba(0,0,0,0.15); }
.spawn-dialog h4 { font-size: 15px; margin-bottom: 12px; }
.spawn-input, .spawn-textarea { width: 100%; padding: 6px 10px; border: 1px solid #E2E6EC; border-radius: 6px; font-size: 14px; margin-bottom: 8px; outline: none; font-family: inherit; box-sizing: border-box; }
.spawn-input:focus, .spawn-textarea:focus { border-color: #6366F1; }
.spawn-actions { display: flex; gap: 8px; justify-content: flex-end; }
.btn-go { padding: 6px 16px; border: none; border-radius: 6px; background: #6366F1; color: white; cursor: pointer; font-size: 13px; }
.btn-go:disabled { background: #A5B4FC; cursor: not-allowed; }
.btn-cancel { padding: 6px 16px; border: 1px solid #E2E6EC; border-radius: 6px; background: white; cursor: pointer; font-size: 13px; }
</style>
