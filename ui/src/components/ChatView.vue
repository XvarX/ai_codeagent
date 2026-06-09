<template>
  <div class="p-[14px_18px] overflow-y-auto flex-1" ref="container">
    <div v-for="(msg, i) in chatStore.messages" :key="i">
      <div v-if="!msg.content || !msg.content.trim()" />
      <div v-else :class="['flex py-[6px] gap-2', msg.role === 'user' ? 'justify-end' : 'justify-start items-start']">
        <div v-if="msg.role === 'assistant'" class="w-7 h-7 rounded-full flex-shrink-0 bg-gradient-to-br from-[#6366F1] to-[#8B5CF6] text-white flex items-center justify-center text-[13px] font-semibold">AI</div>
        <div class="max-w-[75%] px-[14px] py-2 rounded-[14px] text-base leading-relaxed" :class="msg.role === 'user' ? 'bg-surface-2 border border-border-default rounded-br-[3px]' : 'bg-surface-2 border border-border-subtle rounded-tl-[3px]'">
          <div class="bubble-content" v-html="renderMarkdown(msg.content)"></div>
        </div>
      </div>
      <div v-if="msg.diffs && msg.diffs.length" v-for="(diff, di) in msg.diffs" :key="'diff-' + i + '-' + di" class="my-2">
        <DiffViewer :filePath="diff.filePath" :oldContent="diff.oldContent" :newContent="diff.newContent" />
      </div>
    </div>
    <div v-if="chatStore.thinking" class="flex gap-1 py-2 items-center">
      <span class="w-[6px] h-[6px] rounded-[3px] bg-text-muted"></span><span class="w-[6px] h-[6px] rounded-[3px] bg-text-muted"></span><span class="w-[6px] h-[6px] rounded-[3px] bg-text-muted"></span>
      <span class="text-sm text-text-muted ml-[6px]">思考中...</span>
    </div>
    <div v-if="chatStore.currentAssistantMsg" class="flex py-[6px] gap-2 justify-start items-start">
      <div class="w-7 h-7 rounded-full flex-shrink-0 bg-gradient-to-br from-[#6366F1] to-[#8B5CF6] text-white flex items-center justify-center text-[13px] font-semibold">AI</div>
      <div class="max-w-[75%] px-[14px] py-2 rounded-[14px] text-base leading-relaxed bg-surface-2 border border-border-subtle rounded-tl-[3px]">
        <div class="bubble-content" v-html="renderMarkdown(chatStore.currentAssistantMsg)"></div>
      </div>
    </div>
    <div v-for="(diff, di) in chatStore.diffs" :key="'diff-' + di" class="my-2">
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

function isNearBottom(): boolean {
  if (!container.value) return true;
  const el = container.value;
  return el.scrollHeight - el.scrollTop - el.clientHeight < 80;
}

watch(
  () => [chatStore.messages.length, chatStore.currentAssistantMsg.length],
  () => nextTick(() => {
    if (container.value && isNearBottom()) {
      container.value.scrollTop = container.value.scrollHeight;
    }
  })
);
</script>

<style scoped>
.bubble-content :deep(pre) { background: var(--color-surface-2); color: #CDD6F4; padding: 10px 14px; border-radius: 8px; overflow-x: auto; font-family: var(--font-mono); font-size: 14px; line-height: 1.5; margin: 6px 0; }
.bubble-content :deep(code) { font-family: var(--font-mono); font-size: 14px; background: var(--color-surface-3); color: var(--color-text-primary); padding: 1px 5px; border-radius: 4px; }
.bubble-content :deep(pre code) { background: none; padding: 0; border-radius: 0; color: inherit; font-size: 14px; }
.bubble-content :deep(h1), .bubble-content :deep(h2), .bubble-content :deep(h3) { margin: 8px 0 4px; font-weight: 600; color: var(--color-text-primary); }
.bubble-content :deep(h1) { font-size: 20px; }
.bubble-content :deep(h2) { font-size: 17px; }
.bubble-content :deep(h3) { font-size: 15px; }
.bubble-content :deep(ul), .bubble-content :deep(ol) { padding-left: 20px; margin: 4px 0; }
.bubble-content :deep(li) { margin: 2px 0; }
.bubble-content :deep(p) { margin: 4px 0; }
.bubble-content :deep(blockquote) { border-left: 3px solid var(--color-accent); padding-left: 10px; margin: 6px 0; color: var(--color-text-secondary); }
.bubble-content :deep(table) { border-collapse: collapse; margin: 6px 0; font-size: 14px; }
.bubble-content :deep(th), .bubble-content :deep(td) { border: 1px solid var(--color-border-default); padding: 4px 8px; text-align: left; }
.bubble-content :deep(th) { background: var(--color-surface-2); font-weight: 600; }
.bubble-content :deep(strong) { font-weight: 600; }
.bubble-content :deep(em) { font-style: italic; }
.bubble-content :deep(hr) { border: none; border-top: 1px solid var(--color-border-default); margin: 8px 0; }
</style>
