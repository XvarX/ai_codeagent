<template>
  <div class="chat-view" ref="container">
    <div v-for="(msg, i) in chatStore.messages" :key="i" :class="['bubble-row', msg.role]">
      <div v-if="msg.role === 'assistant'" class="avatar">AI</div>
      <div :class="['bubble', msg.role]">
        <div v-if="msg.toolLabels && msg.toolLabels.length" class="tool-labels">
          <div v-for="(tl, ti) in msg.toolLabels" :key="'tl-' + ti" class="tool-label">
            <span class="tl-icon">{{ tl.resultPreview ? (tl.isError ? '&#10007;' : '&#10003;') : '&#128295;' }}</span>
            <span class="tl-name">{{ tl.name }}</span>
            <span v-if="tl.resultPreview" class="tl-result">{{ tl.resultPreview }}</span>
          </div>
        </div>
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
        <div v-if="chatStore.toolLabels && chatStore.toolLabels.length" class="tool-labels">
          <div v-for="(tl, ti) in chatStore.toolLabels" :key="'tl-' + ti" class="tool-label">
            <span class="tl-icon">{{ tl.resultPreview ? (tl.isError ? '&#10007;' : '&#10003;') : '&#128295;' }}</span>
            <span class="tl-name">{{ tl.name }}</span>
            <span v-if="tl.resultPreview" class="tl-result">{{ tl.resultPreview }}</span>
          </div>
        </div>
        <div class="bubble-content" v-html="renderMarkdown(chatStore.currentAssistantMsg)"></div>
      </div>
    </div>
    <div v-for="(diff, di) in chatStore.diffs" :key="'diff-' + di" class="diff-wrapper">
      <DiffViewer
        :filePath="diff.filePath"
        :oldContent="diff.oldContent"
        :newContent="diff.newContent"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { watch, ref, nextTick } from 'vue';
import { useChatStore } from '../stores/chat';
import DiffViewer from './DiffViewer.vue';
import { marked } from 'marked';

const chatStore = useChatStore();
const container = ref<HTMLElement | null>(null);

function renderMarkdown(text: string): string {
  return marked.parse(text, { async: false }) as string;
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
.bubble-content :deep(pre) { background: #1E1E2E; color: #CDD6F4; padding: 10px 14px; border-radius: 8px; overflow-x: auto; font-family: 'Cascadia Code', Consolas, monospace; font-size: 14px; line-height: 1.5; margin: 6px 0; }
.bubble-content :deep(code) { font-family: 'Cascadia Code', Consolas, monospace; font-size: 14px; background: #E8E8EF; padding: 1px 5px; border-radius: 4px; }
.bubble-content :deep(pre code) { background: none; padding: 0; border-radius: 0; font-size: 14px; }
.bubble-content :deep(h1), .bubble-content :deep(h2), .bubble-content :deep(h3) { margin: 8px 0 4px; font-weight: 600; }
.bubble-content :deep(h1) { font-size: 20px; }
.bubble-content :deep(h2) { font-size: 17px; }
.bubble-content :deep(h3) { font-size: 15px; }
.bubble-content :deep(ul), .bubble-content :deep(ol) { padding-left: 20px; margin: 4px 0; }
.bubble-content :deep(li) { margin: 2px 0; }
.bubble-content :deep(p) { margin: 4px 0; }
.bubble-content :deep(blockquote) { border-left: 3px solid #6366F1; padding-left: 10px; margin: 6px 0; color: #64748B; }
.bubble-content :deep(table) { border-collapse: collapse; margin: 6px 0; font-size: 14px; }
.bubble-content :deep(th), .bubble-content :deep(td) { border: 1px solid #DDE0E5; padding: 4px 8px; text-align: left; }
.bubble-content :deep(th) { background: #F1F3F6; font-weight: 600; }
.bubble-content :deep(strong) { font-weight: 600; }
.bubble-content :deep(em) { font-style: italic; }
.bubble-content :deep(hr) { border: none; border-top: 1px solid #E2E6EC; margin: 8px 0; }
.thinking-row { display: flex; gap: 4px; padding: 8px 0; align-items: center; }
.dot { width: 6px; height: 6px; border-radius: 3px; background: #94A3B8; }
.thinking-text { font-size: 14px; color: #94A3B8; }
.diff-wrapper { margin: 8px 0; }
.tool-labels { margin-bottom: 4px; }
.tool-label { display: flex; align-items: center; gap: 4px; font-size: 13px; color: #64748B; padding: 2px 0; }
.tl-icon { font-size: 12px; width: 14px; text-align: center; }
.tl-name { font-weight: 600; color: #475569; }
.tl-result { color: #94A3B8; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
