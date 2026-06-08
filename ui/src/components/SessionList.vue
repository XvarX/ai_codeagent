<template>
  <div class="flex flex-col h-full p-[12px] overflow-y-auto">
    <div class="flex justify-between items-center py-2 border-b border-border-default mb-1">
      <h3 class="text-sm text-text-primary font-semibold">会话</h3>
      <div class="flex gap-1">
        <button class="bg-transparent border border-border-default rounded-[5px] w-6 h-6 cursor-pointer text-sm text-accent inline-flex items-center justify-center hover:bg-surface-2" @click="newChat" title="新对话">+</button>
        <button class="bg-transparent border border-border-default rounded-[5px] w-6 h-6 cursor-pointer text-sm text-accent inline-flex items-center justify-center hover:bg-surface-2" @click="$emit('showMore')" title="更多">···</button>
      </div>
    </div>
    <div class="flex-1 overflow-y-auto">
      <div v-for="proj in sessionStore.openProjects" :key="proj.path" class="mb-[2px]">
        <div class="flex items-center gap-1 p-[6px_8px] cursor-pointer rounded-md hover:bg-surface-2 group" @click="toggleExpand(proj.path)">
          <span class="text-[10px] text-text-secondary flex-shrink-0 transition-transform duration-150" :style="{ transform: proj.expanded ? 'rotate(0deg)' : 'rotate(-90deg)' }">&#9662;</span>
          <span class="text-[13px] font-semibold flex-1 whitespace-nowrap overflow-hidden text-ellipsis" :class="proj.path === sessionStore.currentProjectPath ? 'text-accent' : 'text-text-primary'">{{ proj.name }}</span>
          <span class="flex gap-0.5 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
            <button class="bg-transparent border-none cursor-pointer text-xs w-5 h-5 rounded flex items-center justify-center text-text-muted hover:text-text-secondary hover:bg-surface-3" @click.stop="closeProject(proj.path)" title="关闭项目">&#10005;</button>
            <button class="bg-transparent border-none cursor-pointer text-xs w-5 h-5 rounded flex items-center justify-center text-text-muted hover:text-danger hover:bg-danger-subtle" @click.stop="deleteProject(proj.path)" title="删除项目">&#128465;</button>
          </span>
        </div>
        <div v-if="proj.expanded" class="pl-2">
          <div v-for="s in proj.sessions" :key="s.session_id"
               class="p-[5px_8px] rounded-md cursor-pointer flex flex-col gap-0.5 hover:bg-surface-2 group"
               :class="{ 'bg-accent-subtle': s.session_id === sessionStore.currentSessionId }"
               @click="switchTo(proj.path, s.session_id)">
            <div class="flex items-center gap-[6px]">
              <span class="w-2 h-2 rounded-full flex-shrink-0" :class="dotColor(statusClass(s.session_id))" :style="{ animation: statusClass(s.session_id) === 'dot-running' ? 'pulse 1.5s infinite' : '' }"></span>
              <span class="text-[13px] font-medium text-text-primary whitespace-nowrap overflow-hidden text-ellipsis flex-1">{{ s.title }}</span>
              <span class="flex gap-0.5 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity duration-150 ml-auto">
                <button class="bg-transparent border-none cursor-pointer text-xs w-5 h-5 rounded flex items-center justify-center text-text-muted hover:text-text-secondary hover:bg-surface-3" @click.stop="closeSession(s.session_id)" title="关闭会话">&#10005;</button>
                <button class="bg-transparent border-none cursor-pointer text-xs w-5 h-5 rounded flex items-center justify-center text-text-muted hover:text-danger hover:bg-danger-subtle" @click.stop="deleteSession(s.session_id)" title="删除会话">&#128465;</button>
              </span>
            </div>
            <span class="text-[11px] text-text-muted pl-[14px]">{{ s.msg_count }}条 · {{ formatTime(s.updated_at) }}</span>
          </div>
          <div v-if="!proj.sessions.length" class="text-text-muted text-[13px] py-3 text-center">
            暂无对话
          </div>
        </div>
      </div>
      <div v-if="!sessionStore.openProjects.length" class="text-text-muted text-[13px] py-3 text-center">
        暂无项目，点击上方选择项目
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

function toggleExpand(path: string) {
  sessionStore.toggleProjectExpand(path);
}

function switchTo(projectPath: string, sessionId: string) {
  if (sessionId === sessionStore.currentSessionId) return;
  // Always load to ensure slot exists in backend
  sessionStore.switchToSession(projectPath, sessionId);
}

function closeProject(path: string) {
  sessionStore.closeProject(path);
}

function deleteProject(path: string) {
  if (confirm('确定删除该项目及所有会话数据？此操作不可恢复。')) {
    sessionStore.deleteProject(path);
  }
}

function closeSession(id: string) {
  sessionStore.closeSession(id);
}

function deleteSession(id: string) {
  if (confirm('确定删除该会话？此操作不可恢复。')) {
    sessionStore.deleteSession(id);
  }
}

function statusClass(sessionId: string): string {
  const status = sessionStore.sessionStatuses[sessionId] || 'idle';
  return `dot-${status}`;
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

function dotColor(cls: string): string {
  if (cls === 'dot-running') return 'bg-success';
  if (cls === 'dot-error') return 'bg-danger';
  return 'bg-text-muted';
}
</script>

<style scoped>
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
</style>
