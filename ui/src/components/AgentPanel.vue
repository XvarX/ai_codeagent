<template>
  <div class="bg-surface-1 border-t border-border-default flex flex-col select-none">
    <!-- Resize handle -->
    <div
      class="h-[4px] cursor-ns-resize hover:bg-accent/30 flex-shrink-0"
      @mousedown="onResizeStart"
    ></div>

    <!-- Tab bar -->
    <div class="flex items-center h-9 px-2 gap-1 flex-shrink-0">
      <button
        class="bg-transparent border-none cursor-pointer text-xs text-text-muted p-1 hover:text-text-primary leading-none"
        @click="expanded = !expanded"
        :title="expanded ? '收起' : '展开'"
      >{{ expanded ? '▼' : '▶' }}</button>

      <div
        v-for="agent in agentStore.agents"
        :key="agent.id"
        class="flex items-center gap-[6px] px-[10px] py-[5px] rounded-md cursor-pointer text-[13px] border border-transparent transition-colors hover:bg-surface-2"
        :class="agent.id === agentStore.activeAgentId ? 'bg-accent-subtle border-border-default' : ''"
        @click="switchTo(agent.id)"
      >
        <span class="w-2 h-2 rounded-full flex-shrink-0" :style="{ backgroundColor: statusColor(agent.status) }"></span>
        <span class="text-text-primary whitespace-nowrap">{{ agent.name }}</span>
        <span v-if="agent.est_tokens" class="text-[11px] text-text-muted ml-1">~{{ agent.est_tokens }}t</span>
        <button
          v-if="agent.id !== '1'"
          class="bg-transparent border-none text-text-muted cursor-pointer text-sm leading-none px-1 hover:text-danger ml-1"
          @click.stop="kill(agent.id)"
          title="Kill"
        >&times;</button>
      </div>

      <button
        class="bg-transparent border border-dashed border-border-default rounded-md px-[10px] py-[5px] cursor-pointer text-sm text-accent hover:bg-surface-2 flex items-center gap-1"
        @click="showSpawn = true"
        title="Spawn agent"
      >+</button>

      <div class="flex-1"></div>
      <ChatRoomButton />
    </div>

    <!-- Expanded detail area -->
    <div
      v-if="expanded"
      class="border-t border-border-subtle overflow-y-auto bg-surface-0 text-[13px]"
      :style="{ height: panelHeight + 'px' }"
    >
      <div v-if="!activeAgent" class="text-text-muted text-center py-6">选择 Agent 查看详情</div>
      <div v-else class="p-3">
        <div class="flex items-center gap-2 mb-3">
          <span class="w-[10px] h-[10px] rounded-full flex-shrink-0" :style="{ backgroundColor: statusColor(activeAgent.status) }"></span>
          <span class="font-semibold text-text-primary text-sm">{{ activeAgent.name }}</span>
          <span class="text-text-muted text-xs">({{ activeAgent.status }})</span>
          <span v-if="activeAgent.est_tokens" class="text-text-muted text-xs">~{{ activeAgent.est_tokens }}t</span>
        </div>
        <div class="space-y-1">
          <div
            v-for="(ev, i) in (activeDebugEvents.length ? activeDebugEvents : [])"
            :key="i"
            class="p-[2px_6px] border-b border-border-subtle"
          >
            <span class="font-semibold" :style="{ color: ev.color }">{{ ev.prefix }}</span>
            <span class="text-text-secondary ml-1 whitespace-pre-wrap">{{ ev.message }}</span>
          </div>
          <div v-if="!activeDebugEvents.length" class="text-text-muted text-xs py-4 text-center">暂无事件</div>
        </div>
      </div>
    </div>

    <!-- Spawn overlay -->
    <Teleport to="body">
      <div v-if="showSpawn" class="fixed inset-0 bg-black/50 flex items-center justify-center z-[200]" @click.self="showSpawn = false">
        <div class="bg-surface-1 rounded-xl p-5 min-w-[320px] shadow-dialog">
          <h4 class="text-sm font-semibold mb-3 text-text-primary">Spawn Agent</h4>
          <input v-model="spawnName" placeholder="Agent name" class="w-full p-[6px_10px] border border-border-default rounded-md text-sm mb-2 outline-none bg-surface-2 text-text-primary placeholder:text-text-muted focus:border-accent box-border font-sans" />
          <textarea v-model="spawnPrompt" placeholder="Task prompt..." class="w-full p-[6px_10px] border border-border-default rounded-md text-sm mb-2 outline-none bg-surface-2 text-text-primary placeholder:text-text-muted focus:border-accent box-border font-sans resize-none" rows="3"></textarea>
          <div class="flex gap-2 justify-end">
            <button class="px-4 py-[6px] border-none rounded-md bg-accent text-white cursor-pointer text-[13px] disabled:bg-accent-muted disabled:cursor-not-allowed hover:bg-accent-hover" @click="spawn" :disabled="!spawnName.trim() || !spawnPrompt.trim()">Go</button>
            <button class="px-4 py-[6px] border border-border-default rounded-md bg-transparent cursor-pointer text-[13px] text-text-primary hover:bg-surface-2" @click="showSpawn = false">Cancel</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useAgentStore } from '../stores/agent';
import { agentWs } from '../services/agentWs';
import ChatRoomButton from './ChatRoomButton.vue';

const agentStore = useAgentStore();
const expanded = ref(false);
const panelHeight = ref(200);
const showSpawn = ref(false);
const spawnName = ref('');
const spawnPrompt = ref('');

const activeAgent = computed(() => {
  return agentStore.agents.find(a => a.id === agentStore.activeAgentId) || null;
});

const activeDebugEvents = computed<{prefix: string; message: string; color: string}[]>(() => {
  return [];
});

function statusColor(status: string): string {
  switch (status) {
    case 'running': return '#22C55E';
    case 'completed': return '#3B82F6';
    case 'failed':
    case 'error': return '#EF4444';
    case 'killed': return '#6B7280';
    case 'pending': return '#F59E0B';
    default: return '#868E96';
  }
}

function switchTo(id: string) {
  if (id !== agentStore.activeAgentId) {
    agentWs.send({ type: 'switch_agent', agent_id: id });
  }
  expanded.value = true;
}

function spawn() {
  agentWs.send({ type: 'spawn_agent', agent_name: spawnName.value.trim(), prompt: spawnPrompt.value.trim() });
  showSpawn.value = false;
  spawnName.value = '';
  spawnPrompt.value = '';
  expanded.value = true;
}

function kill(id: string) {
  agentWs.send({ type: 'kill_agent', agent_id: id });
}

let resizing = false;

function onResizeStart(e: MouseEvent) {
  resizing = true;
  const startY = e.clientY;
  const startHeight = panelHeight.value;

  function onMove(ev: MouseEvent) {
    if (!resizing) return;
    const dy = startY - ev.clientY;
    panelHeight.value = Math.min(400, Math.max(80, startHeight + dy));
  }

  function onUp() {
    resizing = false;
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }

  document.body.style.cursor = 'ns-resize';
  document.body.style.userSelect = 'none';
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
}
</script>
