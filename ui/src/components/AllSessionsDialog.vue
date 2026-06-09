<template>
  <div class="fixed inset-0 bg-black/50 flex items-center justify-center z-[200]" @click.self="$emit('close')">
    <div class="bg-surface-1 rounded-[10px] p-5 min-w-[480px] max-h-[60vh] flex flex-col shadow-dialog">
      <h3 class="text-base font-semibold mb-3 text-text-primary">所有对话</h3>
      <div class="mb-2">
        <input v-model="search" placeholder="搜索对话..." class="w-full p-[6px_10px] border border-border-default rounded-md text-sm outline-none bg-surface-2 text-text-primary placeholder:text-text-muted focus:border-accent box-border" />
      </div>
      <div class="overflow-y-auto flex-1">
        <div v-for="s in filtered" :key="s.session_id" class="p-[8px_10px] rounded-md cursor-pointer flex flex-col gap-1 hover:bg-surface-2" @click="load(s)">
          <span class="text-sm font-medium text-text-primary">{{ s.title }}</span>
          <div class="flex gap-2 text-xs text-text-muted">
            <span v-if="s.project_name" class="text-accent">{{ s.project_name }}</span>
            <span>{{ s.msg_count }}条 · {{ formatTime(s.updated_at) }}</span>
          </div>
        </div>
        <div v-if="!filtered.length" class="text-text-muted text-[13px] py-4 text-center">没有找到对话</div>
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
