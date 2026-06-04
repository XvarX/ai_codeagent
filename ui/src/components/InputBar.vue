<template>
  <div class="input-bar">
    <div class="input-wrapper">
      <textarea
        ref="textareaRef"
        v-model="text"
        class="input-field"
        rows="1"
        :placeholder="agentStore.compacting ? 'Compacting...' : (agentStore.busy ? 'Working...' : '输入消息... (Ctrl+Enter 发送)')"
        :disabled="agentStore.busy || agentStore.compacting"
        @keydown="onKeydown"
        @input="autoResize"
      ></textarea>
    </div>
    <div class="input-buttons">
      <button v-if="agentStore.busy" class="btn-stop" @click="stop" title="Stop">■</button>
      <button class="btn-send" :disabled="agentStore.busy || agentStore.compacting || !text.trim()" @click="send" title="Send">↑</button>
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

<style scoped>
.input-bar { display: flex; align-items: flex-end; gap: 8px; padding: 10px 18px; background: #FAFBFC; border-top: 1px solid #F1F3F6; }
.input-wrapper { flex: 1; border: 1px solid #E2E6EC; border-radius: 10px; padding: 10px 14px; background: white; }
.input-field { width: 100%; border: none; outline: none; resize: none; font-size: 17px; color: #1E1B3A; font-family: inherit; min-height: 24px; max-height: 150px; }
.input-field::placeholder { color: #64748B; }
.input-field:disabled { background: transparent; color: #94A3B8; }
.input-buttons { display: flex; flex-direction: column; gap: 4px; }
.btn-send { width: 34px; height: 34px; border-radius: 9px; border: none; background: #6366F1; color: white; font-size: 16px; cursor: pointer; transition: background 0.15s; }
.btn-send:disabled { background: #A5B4FC; cursor: not-allowed; }
.btn-stop { width: 34px; height: 34px; border-radius: 9px; border: none; background: #EF4444; color: white; font-size: 14px; cursor: pointer; }
</style>
