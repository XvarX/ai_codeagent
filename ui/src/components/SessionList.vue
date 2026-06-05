<template>
  <div class="session-list">
    <div class="session-header">
      <h3>{{ sessionStore.currentProjectName || 'Sessions' }}</h3>
      <div class="session-actions">
        <button class="btn-new" @click="newChat" title="新对话">+</button>
        <button class="btn-more" @click="$emit('showMore')" title="更多">···</button>
      </div>
    </div>
    <div class="session-items">
      <div v-for="s in sessionStore.sessions" :key="s.session_id"
           :class="['session-item', { active: s.session_id === sessionStore.currentSessionId }]"
           @click="switchSession(s.session_id)">
        <span class="session-title">{{ s.title }}</span>
        <span class="session-meta">{{ s.msg_count }}条 · {{ formatTime(s.updated_at) }}</span>
      </div>
      <div v-if="!sessionStore.sessions.length" class="session-empty">
        暂无对话，点击 + 开始
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useSessionStore } from '../stores/session';

defineEmits(['showMore']);
const sessionStore = useSessionStore();

function newChat() {
  sessionStore.createSession();
}

function switchSession(id: string) {
  if (id === sessionStore.currentSessionId) return;
  sessionStore.switchSession(id);
}

function formatTime(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return '刚刚';
  if (diffMin < 60) return `${diffMin}分钟前`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}小时前`;
  return `${d.getMonth() + 1}/${d.getDate()}`;
}
</script>

<style scoped>
.session-list { display: flex; flex-direction: column; height: 100%; }
.session-header { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #F1F3F6; margin-bottom: 4px; }
.session-header h3 { font-size: 14px; color: #1E1B3A; }
.session-actions { display: flex; gap: 4px; }
.btn-new, .btn-more { background: none; border: 1px solid #E2E6EC; border-radius: 5px; width: 24px; height: 24px; cursor: pointer; font-size: 14px; color: #6366F1; display: flex; align-items: center; justify-content: center; }
.session-items { flex: 1; overflow-y: auto; }
.session-item { padding: 6px 8px; border-radius: 6px; cursor: pointer; display: flex; flex-direction: column; gap: 2px; }
.session-item:hover { background: #F1F3F6; }
.session-item.active { background: #EBF5FF; }
.session-title { font-size: 13px; font-weight: 500; color: #1E1B3A; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.session-meta { font-size: 11px; color: #94A3B8; }
.session-empty { color: #94A3B8; font-size: 13px; padding: 16px 0; text-align: center; }
</style>
