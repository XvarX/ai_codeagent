<template>
  <div class="chat-view" ref="container">
    <div v-for="(msg, i) in chatStore.messages" :key="i" :class="['bubble-row', msg.role]">
      <div v-if="msg.role === 'assistant'" class="avatar">AI</div>
      <div :class="['bubble', msg.role]">
        <div class="bubble-content" v-html="renderMarkdown(msg.content)"></div>
      </div>
    </div>
    <div v-if="chatStore.thinking" class="thinking-row">
      <span class="dot"></span><span class="dot"></span><span class="dot"></span>
      <span class="thinking-text">思考中...</span>
    </div>
    <div v-if="chatStore.currentAssistantMsg" class="bubble-row assistant">
      <div class="avatar">AI</div>
      <div class="bubble assistant">
        <div class="bubble-content" v-html="renderMarkdown(chatStore.currentAssistantMsg)"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { watch, ref, nextTick } from 'vue';
import { useChatStore } from '../stores/chat';

const chatStore = useChatStore();
const container = ref<HTMLElement | null>(null);

function renderMarkdown(text: string): string {
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  // Fenced code blocks
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Line breaks
  html = html.replace(/\n/g, '<br>');
  return html;
}

watch(
  () => [chatStore.messages.length, chatStore.currentAssistantMsg.length],
  () => nextTick(() => {
    if (container.value) container.value.scrollTop = container.value.scrollHeight;
  })
);
</script>

<style scoped>
.chat-view { padding: 14px 18px; overflow-y: auto; flex: 1; }
.bubble-row { display: flex; padding: 6px 0; gap: 8px; }
.bubble-row.user { justify-content: flex-end; }
.bubble-row.assistant { justify-content: flex-start; align-items: flex-start; }
.avatar {
  width: 28px; height: 28px; border-radius: 14px; flex-shrink: 0;
  background: linear-gradient(135deg, #6366F1, #8B5CF6); color: white;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600;
}
.bubble { max-width: 75%; padding: 8px 14px; border-radius: 14px; font-size: 16px; line-height: 1.5; }
.bubble.user { background: #F1F3F6; border: 1px solid #EAEAEF; border-bottom-right-radius: 3px; }
.bubble.assistant { background: #EBEEF2; border: 1px solid #DDE0E5; border-top-left-radius: 3px; }
.bubble-content :deep(pre) { background: #f0f0f0; padding: 8px; border-radius: 6px; overflow-x: auto; font-family: Consolas, monospace; font-size: 15px; }
.bubble-content :deep(code) { font-family: Consolas, monospace; font-size: 15px; background: #f0f0f0; padding: 1px 4px; border-radius: 3px; }
.thinking-row { display: flex; gap: 4px; padding: 8px 0; align-items: center; }
.dot { width: 6px; height: 6px; border-radius: 3px; background: #94A3B8; }
.thinking-text { font-size: 14px; color: #94A3B8; }
</style>
