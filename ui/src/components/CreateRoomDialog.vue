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
