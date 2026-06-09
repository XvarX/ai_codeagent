<template>
  <div class="fixed inset-0 bg-black/50 flex items-center justify-center z-[200]" @click.self="$emit('close')">
    <div class="bg-surface-1 rounded-[10px] p-5 min-w-[420px] max-h-[60vh] flex flex-col shadow-dialog">
      <h3 class="text-base font-semibold mb-3 text-text-primary">选择项目</h3>
      <div class="flex gap-2 mb-3">
        <input v-model="search" placeholder="输入项目路径..." class="flex-1 p-[6px_10px] border border-border-default rounded-md text-sm outline-none bg-surface-2 text-text-primary placeholder:text-text-muted focus:border-accent" />
        <button class="px-3 py-[6px] border border-border-default rounded-md bg-transparent text-text-primary cursor-pointer text-[13px] hover:bg-surface-2" @click="browseFolder">浏览</button>
        <button class="px-4 py-[6px] border-none rounded-md bg-accent text-white cursor-pointer text-[13px] disabled:bg-accent-muted disabled:cursor-not-allowed" @click="openPath" :disabled="!search.trim()">打开</button>
      </div>
      <div class="overflow-y-auto flex-1">
        <div v-for="p in filteredProjects" :key="p.path"
             class="p-[8px_10px] rounded-md cursor-pointer flex flex-col gap-0.5 hover:bg-surface-2"
             @click="selectProject(p.path)">
          <span class="text-sm font-medium text-text-primary">{{ p.name }}</span>
          <span class="text-xs text-text-muted">{{ p.path }}</span>
        </div>
        <div v-if="!filteredProjects.length" class="text-text-muted text-[13px] py-4 text-center">
          没有历史项目，请输入路径打开
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { open } from '@tauri-apps/plugin-dialog';
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

async function browseFolder() {
  const selected = await open({ directory: true, multiple: false, title: '选择项目目录' });
  if (selected) {
    search.value = selected;
  }
}
</script>
