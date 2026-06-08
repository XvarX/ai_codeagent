<template>
  <div class="border-r border-t border-border-default bg-surface-1 flex flex-col transition-[width,min-width] duration-200 ease-in-out overflow-hidden"
       :class="collapsed ? 'w-[36px] min-w-[36px] p-[12px_0] items-center' : 'w-[160px] min-w-[160px]'">
    <button class="bg-transparent border-none cursor-pointer text-xs text-text-muted p-1 flex-shrink-0 w-5 h-5 flex items-center justify-center rounded hover:bg-surface-2 hover:text-accent"
            @click="collapsed = !collapsed" :title="collapsed ? 'Expand' : 'Collapse'">
      {{ collapsed ? '▶' : '◀' }}
    </button>

    <template v-if="!collapsed">
      <div class="p-[12px] flex flex-col flex-1 overflow-y-auto">
        <div class="flex justify-between items-center mb-2">
          <h3 class="text-sm text-text-primary font-semibold">Agents</h3>
          <button class="w-[22px] h-[22px] rounded-[5px] border border-border-default bg-transparent cursor-pointer text-sm text-accent flex-shrink-0 hover:bg-surface-2" @click="showSpawn = true" title="Spawn">+</button>
        </div>
        <div class="flex-1">
          <div v-for="agent in agentStore.agents" :key="agent.id"
               class="flex justify-between items-center p-[6px_8px] rounded-md cursor-pointer text-[13px] hover:bg-surface-2"
               :class="{ 'bg-accent-subtle': agent.id === agentStore.activeAgentId }"
               @click="switchTo(agent.id)">
            <div class="flex flex-col min-w-0">
              <span class="font-medium text-text-primary whitespace-nowrap overflow-hidden text-ellipsis">{{ agent.name }}</span>
              <div class="flex items-center gap-[6px] mt-px">
                <span v-if="agent.id === 'master'" class="text-[11px] text-text-muted">主 Agent</span>
                <span v-if="agent.est_tokens" class="text-[11px] text-accent">~{{ agent.est_tokens }}t</span>
              </div>
            </div>
            <div class="flex items-center gap-1 flex-shrink-0">
              <span class="w-2 h-2 rounded flex-shrink-0" :style="{ backgroundColor: statusColor(agent.status) }"></span>
              <button v-if="agent.id !== 'master'" class="bg-transparent border-none text-text-muted cursor-pointer text-sm px-0.5 hover:text-danger" @click.stop="kill(agent.id)" title="Kill">&times;</button>
            </div>
          </div>
        </div>
        <div v-if="!agentStore.agents.length" class="text-text-muted text-[13px] p-2">No agents</div>
      </div>

      <!-- Spawn dialog -->
      <div v-if="showSpawn" class="fixed inset-0 bg-black/20 flex items-center justify-center z-[200]" @click.self="showSpawn = false">
        <div class="bg-surface-1 rounded-[10px] p-5 min-w-[300px] shadow-dialog">
          <h4 class="text-sm font-semibold mb-3 text-text-primary">Spawn Agent</h4>
          <input v-model="spawnName" placeholder="Agent name" class="w-full p-[6px_10px] border border-border-default rounded-md text-sm mb-2 outline-none font-sans box-border bg-surface-2 text-text-primary placeholder:text-text-muted focus:border-accent" />
          <textarea v-model="spawnPrompt" placeholder="Task prompt..." class="w-full p-[6px_10px] border border-border-default rounded-md text-sm mb-2 outline-none font-sans box-border bg-surface-2 text-text-primary placeholder:text-text-muted focus:border-accent resize-none" rows="3"></textarea>
          <div class="flex gap-2 justify-end">
            <button class="px-4 py-[6px] border-none rounded-md bg-accent text-white cursor-pointer text-[13px] disabled:bg-accent-muted disabled:cursor-not-allowed" @click="spawn" :disabled="!spawnName.trim() || !spawnPrompt.trim()">Go</button>
            <button class="px-4 py-[6px] border border-border-default rounded-md bg-transparent cursor-pointer text-[13px] text-text-primary hover:bg-surface-2" @click="showSpawn = false">Cancel</button>
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
