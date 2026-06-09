<template>
  <div class="flex items-end gap-2 p-[10px_18px] bg-surface-1 border-t border-border-default">
    <div class="flex-1 border border-border-default rounded-[10px] p-[10px_14px] bg-surface-2">
      <textarea
        ref="textareaRef"
        v-model="text"
        class="w-full border-none outline-none resize-none text-[17px] text-text-primary font-sans bg-transparent min-h-6 max-h-[150px] placeholder:text-text-secondary disabled:text-text-muted"
        rows="1"
        :placeholder="agentStore.compacting ? 'Compacting...' : (agentStore.busy ? 'Working...' : '输入消息... (Ctrl+Enter 发送)')"
        :disabled="agentStore.busy || agentStore.compacting"
        @keydown="onKeydown"
        @input="autoResize"
      ></textarea>
    </div>
    <div class="flex flex-col gap-1">
      <button v-if="agentStore.busy" class="w-[34px] h-[34px] rounded-[9px] border-none bg-danger text-white text-sm cursor-pointer" @click="stop" title="Stop">■</button>
      <button class="w-[34px] h-[34px] rounded-[9px] border-none bg-accent text-white text-base cursor-pointer transition-colors disabled:bg-accent-muted disabled:cursor-not-allowed" :disabled="agentStore.busy || agentStore.compacting || !text.trim()" @click="send" title="Send">↑</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue';
import { useAgentStore } from '../stores/agent';
import { useChatStore } from '../stores/chat';
import { agentWs } from '../services/agentWs';

const agentStore = useAgentStore();
const chatStore = useChatStore();
const text = ref('');
const textareaRef = ref<HTMLTextAreaElement | null>(null);

function autoResize() {
  const el = textareaRef.value;
  if (!el) return;
  el.style.height = 'auto';
  el.style.height = el.scrollHeight + 'px';
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    send();
  }
}

function send() {
  const msg = text.value.trim();
  if (!msg) return;

  // Intercept /compact command
  if (msg === '/compact') {
    agentWs.send({ type: 'compact' });
    text.value = '';
    resetTextareaHeight();
    return;
  }

  chatStore.addUserMessage(msg);
  agentWs.send({ type: 'send_message', text: msg });
  text.value = '';
  resetTextareaHeight();
}

function resetTextareaHeight() {
  nextTick(() => {
    const el = textareaRef.value;
    if (el) {
      el.style.height = 'auto';
    }
  });
}

function stop() {
  agentWs.send({ type: 'cancel' });
}
</script>
