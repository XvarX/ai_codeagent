<template>
  <div class="session-overlay" @click.self="$emit('close')">
    <div class="session-dialog">
      <h3>所有对话</h3>
      <div class="session-search">
        <input v-model="search" placeholder="搜索对话..." class="session-input" />
      </div>
      <div class="all-sessions">
        <div v-for="s in filtered" :key="s.session_id" class="all-session-item" @click="load(s)">
          <span class="all-session-title">{{ s.title }}</span>
          <div class="all-session-meta">
            <span v-if="s.project_name" class="all-session-project">{{ s.project_name }}</span>
            <span>{{ s.msg_count }}条 · {{ formatTime(s.updated_at) }}</span>
          </div>
        </div>
        <div v-if="!filtered.length" class="session-empty">没有找到对话</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useSessionStore, type SessionInfo } from '../stores/session';
import { agentWs } from '../services/agentWs';

defineEmits(['close']);
const sessionStore = useSessionStore();
const search = ref('');
const allSessions = ref<SessionInfo[]>([]);

onMounted(() => {
  agentWs.send({ type: 'list_all_sessions' });
  agentWs.on('all_sessions', (d: any) => {
    allSessions.value = d.sessions || [];
  });
});

const filtered = computed(() => {
  if (!search.value.trim()) return allSessions.value;
  const q = search.value.toLowerCase();
  return allSessions.value.filter(s =>
    s.title.toLowerCase().includes(q) ||
    (s.project_name || '').toLowerCase().includes(q)
  );
});

function load(s: SessionInfo) {
  if (s.project_path) {
    sessionStore.openProject(s.project_path);
    setTimeout(() => sessionStore.loadSession(s.session_id), 100);
  }
}

function formatTime(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
}
</script>

<style scoped>
.session-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.2); display: flex; align-items: center; justify-content: center; z-index: 200; }
.session-dialog { background: white; border-radius: 10px; padding: 20px; min-width: 480px; max-height: 60vh; display: flex; flex-direction: column; box-shadow: 0 4px 20px rgba(0,0,0,0.15); }
.session-dialog h3 { font-size: 16px; margin-bottom: 12px; }
.session-input { width: 100%; padding: 6px 10px; border: 1px solid #E2E6EC; border-radius: 6px; font-size: 14px; outline: none; margin-bottom: 8px; box-sizing: border-box; }
.session-input:focus { border-color: #6366F1; }
.all-sessions { overflow-y: auto; flex: 1; }
.all-session-item { padding: 8px 10px; border-radius: 6px; cursor: pointer; display: flex; flex-direction: column; gap: 4px; }
.all-session-item:hover { background: #F1F3F6; }
.all-session-title { font-size: 14px; font-weight: 500; color: #1E1B3A; }
.all-session-meta { display: flex; gap: 8px; font-size: 12px; color: #94A3B8; }
.all-session-project { color: #6366F1; }
.session-empty { color: #94A3B8; font-size: 13px; padding: 16px 0; text-align: center; }
</style>
