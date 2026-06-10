<template>
  <teleport to="body">
    <div
      v-if="room"
      class="bg-surface-1 border border-border-default flex flex-col"
      :class="maximized ? '' : 'rounded-lg'"
      :style="{ position: 'fixed', ...dialogStyle }"
    >
      <!-- Title bar (draggable, double-click to maximize) -->
      <div
        class="flex items-center bg-surface-2 border-b border-border-default cursor-move shrink-0 px-3 py-1.5"
        @mousedown.prevent="startDrag($event)"
        @dblclick.prevent="toggleMaximize()"
      >
        <span class="text-xs text-text-primary font-medium">💬 {{ room.name }}</span>
        <span class="text-[10px] text-text-muted ml-2">{{ room.agentIds.length + 1 }} 人</span>
        <div class="flex-1"></div>
        <button
          class="bg-transparent border-none text-text-muted hover:text-text-primary text-sm cursor-pointer px-1"
          @click.stop="chatStore.activeRoomId = null"
        >✕</button>
      </div>

      <!-- Body: sidebar + chat -->
      <div class="flex flex-1 overflow-hidden">
        <!-- Member list sidebar -->
        <div class="w-[140px] border-r border-border-subtle p-2 flex flex-col gap-1 shrink-0 overflow-y-auto">
          <div class="flex items-center gap-1.5 px-2 py-1 rounded text-xs text-text-primary">
            <span class="w-1.5 h-1.5 rounded-full bg-blue-400 shrink-0"></span>
            <span>👤 你</span>
          </div>
          <div
            v-for="agent in memberAgents"
            :key="agent.id"
            class="flex items-center gap-1.5 px-2 py-1 rounded text-xs hover:bg-surface-2 transition-colors duration-200"
          >
            <span
              class="w-1.5 h-1.5 rounded-full shrink-0"
              :class="agent.status === 'running' ? 'bg-success' : 'bg-text-muted'"
            ></span>
            <span :style="{ color: agent.color }">{{ agent.name }}</span>
          </div>
        </div>

        <!-- Message stream -->
        <div class="flex-1 flex flex-col overflow-hidden">
          <div ref="msgContainer" class="flex-1 overflow-y-auto p-3 flex flex-col gap-3">
            <div
              v-for="msg in messages"
              :key="msg.id"
              class="flex"
              :class="msg.senderId === 'user' ? 'justify-end' : 'justify-start'"
            >
              <div class="flex flex-col max-w-[75%]">
                <span
                  v-if="msg.senderId !== 'user'"
                  class="text-[10px] mb-0.5"
                  :style="{ color: msg.senderColor }"
                >@{{ msg.senderName }}</span>
                <div
                  class="px-3 py-2 rounded-xl text-xs whitespace-pre-wrap break-all"
                  :class="msg.senderId === 'user'
                    ? 'bg-accent text-white rounded-br-sm'
                    : 'bg-surface-3 text-text-primary rounded-bl-sm'"
                >
                  {{ msg.content }}
                  <span
                    v-if="msg.isStreaming"
                    class="inline-block w-1.5 h-3.5 bg-text-muted animate-pulse ml-0.5 align-middle"
                  ></span>
                </div>
              </div>
            </div>
          </div>

          <!-- Input bar -->
          <div class="px-3 py-2 border-t border-border-subtle flex gap-2">
            <input
              v-model="inputText"
              class="flex-1 bg-surface-2 border border-border-default rounded-md px-3 py-2 text-sm text-text-primary outline-none focus:border-accent min-h-[44px]"
              placeholder="@name 或输入消息..."
              @keydown.ctrl.enter="send"
              @keydown.enter="send"
            />
            <button
              class="bg-accent text-white text-xs px-4 py-2 rounded-md cursor-pointer hover:bg-accent-hover border-none"
              @click="send"
            >发送</button>
          </div>
        </div>
      </div>

      <!-- Bottom resize handle -->
      <div
        v-if="!maximized"
        class="h-2 cursor-ns-resize hover:bg-accent/20 shrink-0"
        @mousedown.prevent="startResize($event, 'vertical')"
      ></div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useChatStore } from '../stores/chat'
import { useAgentStore } from '../stores/agent'

const chatStore = useChatStore()
const agentStore = useAgentStore()

const dialogX = ref(80)
const dialogY = ref(80)
const dialogWidth = ref(700)
const dialogHeight = ref(500)
const minWidth = 400
const minHeight = 300
const maximized = ref(false)
const savedRect = { x: 80, y: 80, w: 700, h: 500 }
const inputText = ref('')
const msgContainer = ref<HTMLElement | null>(null)

const room = computed(() =>
  chatStore.rooms.find(r => r.id === chatStore.activeRoomId) || null
)

const messages = computed(() =>
  chatStore.roomMessages.get(chatStore.activeRoomId ?? '') || []
)

const memberAgents = computed(() => {
  if (!room.value) return []
  return room.value.agentIds.map(id => {
    const agent = agentStore.agents.find(a => a.id === id)
    return {
      id,
      name: agent?.name || id,
      status: agent?.status || 'idle',
      color: agentStore.getAgentColor(id),
    }
  })
})

const dialogStyle = computed(() => ({
  left: dialogX.value + 'px',
  top: dialogY.value + 'px',
  width: dialogWidth.value + 'px',
  height: dialogHeight.value + 'px',
  zIndex: 50,
  boxShadow: maximized.value ? 'none' : '0 8px 32px rgba(0, 0, 0, 0.12)',
  borderRadius: maximized.value ? '0' : undefined,
  transition: maximized.value ? 'left 0.15s, top 0.15s, width 0.15s, height 0.15s' : undefined,
}))

function send() {
  const text = inputText.value.trim()
  if (!text || !chatStore.activeRoomId) return
  chatStore.sendRoomMessage(chatStore.activeRoomId, text)
  inputText.value = ''
}

// Auto-scroll to bottom when new messages arrive
watch(
  () => messages.value.length,
  () => {
    nextTick(() => {
      if (msgContainer.value) {
        msgContainer.value.scrollTop = msgContainer.value.scrollHeight
      }
    })
  }
)

function toggleMaximize() {
  if (maximized.value) {
    dialogX.value = savedRect.x
    dialogY.value = savedRect.y
    dialogWidth.value = savedRect.w
    dialogHeight.value = savedRect.h
    maximized.value = false
  } else {
    savedRect.x = dialogX.value
    savedRect.y = dialogY.value
    savedRect.w = dialogWidth.value
    savedRect.h = dialogHeight.value
    const chatArea = document.getElementById('chat-area')
    if (chatArea) {
      const rect = chatArea.getBoundingClientRect()
      dialogX.value = rect.left
      dialogY.value = rect.top
      dialogWidth.value = rect.width
      dialogHeight.value = rect.height
    } else {
      dialogX.value = 0
      dialogY.value = 40
      dialogWidth.value = window.innerWidth
      dialogHeight.value = window.innerHeight - 96
    }
    maximized.value = true
  }
}

function startDrag(e: MouseEvent) {
  if (maximized.value) return
  const startX = e.clientX
  const startY = e.clientY
  const origX = dialogX.value
  const origY = dialogY.value
  function onMove(ev: MouseEvent) {
    dialogX.value = origX + (ev.clientX - startX)
    dialogY.value = Math.max(0, origY + (ev.clientY - startY))
  }
  function onUp() {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

function startResize(e: MouseEvent, direction: 'vertical' | 'horizontal') {
  const startX = e.clientX
  const startY = e.clientY
  const origW = dialogWidth.value
  const origH = dialogHeight.value
  function onMove(ev: MouseEvent) {
    if (direction === 'horizontal') {
      dialogWidth.value = Math.max(minWidth, origW + (ev.clientX - startX))
    } else {
      dialogHeight.value = Math.max(minHeight, origH + (ev.clientY - startY))
    }
  }
  function onUp() {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}
</script>
