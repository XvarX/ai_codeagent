<template>
  <div class="p-[14px_18px] overflow-y-auto flex-1" ref="container">
    <div v-for="(msg, i) in chatStore.messages" :key="i">
      <!-- Empty message skip -->
      <div v-if="!msg.content || !msg.content.trim()" />

      <!-- ===== 聊天室消息 ===== -->
      <div v-else-if="msg.roomInfo"
        :class="['flex py-[6px] gap-2', msg.role === 'user' ? 'justify-end' : 'justify-start items-start']"
      >
        <!-- 左侧头像：AI Agent（活跃Agent自己的聊天室广播） -->
        <div v-if="msg.role === 'assistant'" class="flex flex-col items-center gap-0.5">
          <span v-if="msg.roomInfo.senderName" class="text-[10px] text-text-muted font-medium max-w-[56px] text-center truncate">{{ msg.roomInfo.senderName }}</span>
          <div class="w-7 h-7 rounded-full flex-shrink-0 bg-gradient-to-br from-[#6366F1] to-[#8B5CF6] text-white flex items-center justify-center text-[11px] font-semibold">AI</div>
        </div>

        <div class="flex flex-col max-w-[75%]" :class="msg.role === 'user' ? 'items-end' : 'items-start'">
          <!-- 聊天室标签 -->
          <span class="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full mb-1"
            :class="msg.roomInfo.direction === 'out'
              ? 'text-[#10B981] bg-[rgba(16,185,129,0.08)]'
              : 'text-[#6366F1] bg-[rgba(99,102,241,0.08)]'"
          >
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
              <rect x="1.5" y="2" width="13" height="10" rx="2" stroke="currentColor" stroke-width="1.2"/>
              <line x1="4.5" y1="5.5" x2="11.5" y2="5.5" stroke="currentColor" stroke-width="1"/>
              <line x1="4.5" y1="8.5" x2="9.5" y2="8.5" stroke="currentColor" stroke-width="1"/>
            </svg>
            {{ msg.roomInfo.roomName }}
            <template v-if="msg.roomInfo.replyTo">
              <svg width="10" height="10" viewBox="0 0 16 16" fill="none" class="opacity-60">
                <path d="M3 8h10M10 4l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
              </svg>
              <span class="font-normal opacity-70">{{ msg.roomInfo.replyTo }}</span>
            </template>
          </span>
          <!-- 聊天室气泡 -->
          <div class="px-[14px] py-2 rounded-[14px] text-base leading-relaxed"
            :class="msg.roomInfo.direction === 'out'
              ? 'bg-[rgba(16,185,129,0.04)] border border-[rgba(16,185,129,0.20)] rounded-br-[3px]'
              : msg.role === 'user'
                ? 'bg-[rgba(99,102,241,0.04)] border border-[rgba(99,102,241,0.18)] rounded-br-[3px]'
                : 'bg-[rgba(99,102,241,0.04)] border border-[rgba(99,102,241,0.18)] rounded-tl-[3px]'"
          >
            <div class="bubble-content" v-html="renderMarkdown(msg.content)"></div>
          </div>
        </div>

        <!-- 右侧头像：其他 Agent（AI头像+名字）或用户 -->
        <div v-if="msg.role === 'user'" class="flex flex-col items-center gap-0.5">
          <span v-if="msg.roomInfo.senderName && msg.roomInfo.direction === 'in'" class="text-[10px] text-text-muted font-medium max-w-[56px] text-center truncate">{{ msg.roomInfo.senderName }}</span>
          <div v-if="msg.roomInfo.direction === 'in'" class="w-7 h-7 rounded-full flex-shrink-0 bg-gradient-to-br from-[#6366F1] to-[#8B5CF6] text-white flex items-center justify-center text-[11px] font-semibold">AI</div>
          <div v-else class="w-7 h-7 rounded-full flex-shrink-0 bg-gradient-to-br from-[#3B82F6] to-[#06B6D4] text-white flex items-center justify-center text-[12px] font-semibold">你</div>
        </div>
      </div>

      <!-- ===== 私聊消息 ===== -->
      <div v-else-if="msg.pvtInfo"
        :class="['flex py-[6px] gap-2', msg.pvtInfo.direction === 'out' ? 'justify-start items-start' : 'justify-end']"
      >
        <!-- 左侧头像：Agent发出的私聊 -->
        <div v-if="msg.pvtInfo.direction === 'out'" class="flex flex-col items-center gap-0.5">
          <span class="text-[10px] text-text-muted font-medium max-w-[56px] text-center truncate">AI</span>
          <div class="w-7 h-7 rounded-full flex-shrink-0 bg-gradient-to-br from-[#F59E0B] to-[#D97706] text-white flex items-center justify-center text-[11px] font-semibold">PM</div>
        </div>

        <div class="flex flex-col max-w-[75%]" :class="msg.pvtInfo.direction === 'out' ? 'items-start' : 'items-end'">
          <span class="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full mb-1"
            :class="msg.pvtInfo.direction === 'out'
              ? 'text-[#F59E0B] bg-[rgba(245,158,11,0.08)]'
              : 'text-[#D97706] bg-[rgba(217,119,6,0.08)]'"
          >
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
              <rect x="2" y="3" width="12" height="9" rx="1.5" stroke="currentColor" stroke-width="1.2"/>
              <line x1="5" y1="7" x2="11" y2="7" stroke="currentColor" stroke-width="1"/>
              <line x1="5" y1="10" x2="9" y2="10" stroke="currentColor" stroke-width="1"/>
            </svg>
            To: {{ msg.pvtInfo.targetName }}
          </span>
          <div class="px-[14px] py-2 rounded-[14px] text-base leading-relaxed"
            :class="msg.pvtInfo.direction === 'out'
              ? 'bg-[rgba(245,158,11,0.05)] border border-[rgba(245,158,11,0.25)] rounded-tl-[3px]'
              : 'bg-[rgba(217,119,6,0.04)] border border-[rgba(217,119,6,0.20)] rounded-br-[3px]'"
          >
            <div class="bubble-content" v-html="renderMarkdown(msg.content)"></div>
          </div>
        </div>

        <!-- 右侧头像：Agent收到的私聊 -->
        <div v-if="msg.pvtInfo.direction === 'in'" class="flex flex-col items-center gap-0.5">
          <span v-if="msg.pvtInfo.targetName" class="text-[10px] text-text-muted font-medium max-w-[56px] text-center truncate">{{ msg.pvtInfo.targetName }}</span>
          <div class="w-7 h-7 rounded-full flex-shrink-0 bg-gradient-to-br from-[#D97706] to-[#92400E] text-white flex items-center justify-center text-[11px] font-semibold">PM</div>
        </div>
      </div>

      <!-- ===== 普通消息 ===== -->
      <div v-else :class="['flex py-[6px] gap-2', msg.role === 'user' ? 'justify-end' : 'justify-start items-start']">
        <!-- 左侧 AI 头像 -->
        <div v-if="msg.role === 'assistant'" class="w-7 h-7 rounded-full flex-shrink-0 bg-gradient-to-br from-[#6366F1] to-[#8B5CF6] text-white flex items-center justify-center text-[13px] font-semibold">AI</div>

        <div class="max-w-[75%] px-[14px] py-2 rounded-[14px] text-base leading-relaxed"
          :class="msg.role === 'user'
            ? 'bg-surface-2 border border-border-default rounded-br-[3px]'
            : 'bg-surface-2 border border-border-subtle rounded-tl-[3px]'"
        >
          <div class="bubble-content" v-html="renderMarkdown(msg.content)"></div>
        </div>

        <!-- 右侧用户头像 -->
        <div v-if="msg.role === 'user'" class="w-7 h-7 rounded-full flex-shrink-0 bg-gradient-to-br from-[#3B82F6] to-[#06B6D4] text-white flex items-center justify-center text-[12px] font-semibold">你</div>
      </div>

      <!-- Diffs -->
      <div v-if="msg.diffs && msg.diffs.length" v-for="(diff, di) in msg.diffs" :key="'diff-' + i + '-' + di" class="my-2">
        <DiffViewer :filePath="diff.filePath" :oldContent="diff.oldContent" :newContent="diff.newContent" />
      </div>
    </div>

    <!-- Thinking -->
    <div v-if="chatStore.thinking" class="flex gap-1 py-2 items-center">
      <span class="w-[6px] h-[6px] rounded-[3px] bg-text-muted"></span><span class="w-[6px] h-[6px] rounded-[3px] bg-text-muted"></span><span class="w-[6px] h-[6px] rounded-[3px] bg-text-muted"></span>
      <span class="text-sm text-text-muted ml-[6px]">思考中...</span>
    </div>

    <!-- Streaming message (always active agent on left) -->
    <div v-if="chatStore.currentAssistantMsg" class="flex py-[6px] gap-2 justify-start items-start">
      <div class="w-7 h-7 rounded-full flex-shrink-0 bg-gradient-to-br from-[#6366F1] to-[#8B5CF6] text-white flex items-center justify-center text-[13px] font-semibold">AI</div>
      <div class="max-w-[75%] px-[14px] py-2 rounded-[14px] text-base leading-relaxed bg-surface-2 border border-border-subtle rounded-tl-[3px]">
        <div class="bubble-content" v-html="renderMarkdown(chatStore.currentAssistantMsg)"></div>
      </div>
    </div>

    <!-- Current diffs -->
    <div v-for="(diff, di) in chatStore.diffs" :key="'diff-' + di" class="my-2">
      <DiffViewer :filePath="diff.filePath" :oldContent="diff.oldContent" :newContent="diff.newContent" />
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
.bubble-content :deep(pre) { background: #1E1E2E; color: #CDD6F4; padding: 10px 14px; border-radius: 8px; overflow-x: auto; font-family: var(--font-mono); font-size: 14px; line-height: 1.5; margin: 6px 0; border: 1px solid var(--color-border-subtle); }
.bubble-content :deep(code) { font-family: var(--font-mono); font-size: 14px; background: var(--color-surface-3); color: #D6336C; padding: 1px 5px; border-radius: 4px; }
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
