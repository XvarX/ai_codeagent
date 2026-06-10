<template>
  <div class="flex items-center gap-1.5 ml-2 pl-2 border-l border-border-subtle">
    <span class="text-[10px] text-text-muted shrink-0">💬</span>
    <button
      v-for="room in chatStore.rooms"
      :key="room.id"
      class="px-2.5 py-1 rounded-md text-xs cursor-pointer border-none whitespace-nowrap transition-colors duration-200"
      :class="chatStore.activeRoomId === room.id
        ? 'bg-accent-subtle text-accent'
        : 'bg-surface-2 text-text-secondary hover:bg-surface-3'"
      @click="openRoom(room.id)"
    >{{ room.name }}
      <span class="text-[10px] text-text-muted ml-1">({{ room.agentIds.length }})</span>
    </button>
    <button
      class="bg-transparent border border-dashed border-border-default rounded-md px-2 py-1 cursor-pointer text-xs text-accent hover:bg-surface-2 shrink-0"
      @click="showCreate = true"
    >+ 新建</button>
    <CreateRoomDialog v-if="showCreate" @close="showCreate = false" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useChatStore } from '../stores/chat'
import { agentWs } from '../services/agentWs'
import CreateRoomDialog from './CreateRoomDialog.vue'

const chatStore = useChatStore()
const showCreate = ref(false)

onMounted(() => {
  agentWs.send({ type: 'room_list' })
})

function openRoom(id: string) {
  chatStore.activeRoomId = id
}
</script>
