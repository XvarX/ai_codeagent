<template>
  <div class="picker-overlay" @click.self="$emit('close')">
    <div class="picker-dialog">
      <h3>选择项目</h3>
      <div class="picker-search">
        <input v-model="search" placeholder="输入项目路径..." class="picker-input" />
        <button class="btn-open" @click="openPath" :disabled="!search.trim()">打开</button>
      </div>
      <div class="picker-list">
        <div v-for="p in filteredProjects" :key="p.path"
             class="picker-item" @click="selectProject(p.path)">
          <span class="picker-name">{{ p.name }}</span>
          <span class="picker-path">{{ p.path }}</span>
        </div>
        <div v-if="!filteredProjects.length" class="picker-empty">
          没有历史项目，请输入路径打开
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useSessionStore } from '../stores/session';

defineEmits(['close']);
const sessionStore = useSessionStore();
const search = ref('');

const filteredProjects = computed(() => {
  if (!search.value.trim()) return sessionStore.projects;
  const q = search.value.toLowerCase();
  return sessionStore.projects.filter(
    p => p.name.toLowerCase().includes(q) || p.path.toLowerCase().includes(q)
  );
});

function selectProject(path: string) {
  sessionStore.openProject(path);
}

function openPath() {
  if (search.value.trim()) {
    sessionStore.openProject(search.value.trim());
  }
}
</script>

<style scoped>
.picker-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.2); display: flex; align-items: center; justify-content: center; z-index: 200; }
.picker-dialog { background: white; border-radius: 10px; padding: 20px; min-width: 420px; max-height: 60vh; display: flex; flex-direction: column; box-shadow: 0 4px 20px rgba(0,0,0,0.15); }
.picker-dialog h3 { font-size: 16px; margin-bottom: 12px; }
.picker-search { display: flex; gap: 8px; margin-bottom: 12px; }
.picker-input { flex: 1; padding: 6px 10px; border: 1px solid #E2E6EC; border-radius: 6px; font-size: 14px; outline: none; }
.picker-input:focus { border-color: #6366F1; }
.btn-open { padding: 6px 16px; border: none; border-radius: 6px; background: #6366F1; color: white; cursor: pointer; font-size: 13px; }
.btn-open:disabled { background: #A5B4FC; cursor: not-allowed; }
.picker-list { overflow-y: auto; flex: 1; }
.picker-item { padding: 8px 10px; border-radius: 6px; cursor: pointer; display: flex; flex-direction: column; gap: 2px; }
.picker-item:hover { background: #F1F3F6; }
.picker-name { font-size: 14px; font-weight: 500; color: #1E1B3A; }
.picker-path { font-size: 12px; color: #94A3B8; }
.picker-empty { color: #94A3B8; font-size: 13px; padding: 16px 0; text-align: center; }
</style>
