<template>
  <div class="session-list">
    <div class="session-header">
      <h3>会话</h3>
      <div class="session-actions">
        <button class="btn-new" @click="newChat" title="新对话">+</button>
        <button class="btn-more" @click="$emit('showMore')" title="更多">···</button>
      </div>
    </div>
    <div class="session-items">
      <div v-for="proj in sessionStore.openProjects" :key="proj.path" class="project-group">
        <div class="project-row" @click="toggleExpand(proj.path)">
          <span class="expand-arrow" :class="{ collapsed: !proj.expanded }">&#9662;</span>
          <span class="project-name" :class="{ active: proj.path === sessionStore.currentProjectPath }">{{ proj.name }}</span>
          <span class="action-btns">
            <button class="btn-icon btn-close" @click.stop="closeProject(proj.path)" title="关闭项目">&#10005;</button>
            <button class="btn-icon btn-delete" @click.stop="deleteProject(proj.path)" title="删除项目">&#128465;</button>
          </span>
        </div>
        <div v-if="proj.expanded" class="project-sessions">
          <div v-for="s in proj.sessions" :key="s.session_id"
               :class="['session-item', { active: s.session_id === sessionStore.currentSessionId }]"
               @click="switchTo(proj.path, s.session_id)">
            <div class="session-row">
              <span class="status-dot" :class="statusClass(s.session_id)"></span>
              <span class="session-title">{{ s.title }}</span>
              <span class="action-btns session-action-btns">
                <button class="btn-icon btn-close" @click.stop="closeSession(s.session_id)" title="关闭会话">&#10005;</button>
                <button class="btn-icon btn-delete" @click.stop="deleteSession(s.session_id)" title="删除会话">&#128465;</button>
              </span>
            </div>
            <span class="session-meta">{{ s.msg_count }}条 · {{ formatTime(s.updated_at) }}</span>
          </div>
          <div v-if="!proj.sessions.length" class="session-empty">
            暂无对话
          </div>
        </div>
      </div>
      <div v-if="!sessionStore.openProjects.length" class="session-empty">
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
</script>

<style scoped>
.session-list { display: flex; flex-direction: column; height: 100%; }
.session-header { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #F1F3F6; margin-bottom: 4px; }
.session-header h3 { font-size: 14px; color: #1E1B3A; }
.session-actions { display: flex; gap: 4px; }
.btn-new, .btn-more { background: none; border: 1px solid #E2E6EC; border-radius: 5px; width: 24px; height: 24px; cursor: pointer; font-size: 14px; color: #6366F1; display: flex; align-items: center; justify-content: center; }
.session-items { flex: 1; overflow-y: auto; }

/* Project group */
.project-group { margin-bottom: 2px; }
.project-row { display: flex; align-items: center; gap: 4px; padding: 6px 8px; cursor: pointer; border-radius: 6px; }
.project-row:hover { background: #F1F3F6; }
.expand-arrow { font-size: 10px; color: #64748B; transition: transform 0.15s; flex-shrink: 0; }
.expand-arrow.collapsed { transform: rotate(-90deg); }
.project-name { font-size: 13px; font-weight: 600; color: #1E1B3A; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.project-name.active { color: #6366F1; }

/* Session items */
.project-sessions { padding-left: 8px; }
.session-item { padding: 5px 8px; border-radius: 6px; cursor: pointer; display: flex; flex-direction: column; gap: 2px; }
.session-item:hover { background: #F1F3F6; }
.session-item.active { background: #EBF5FF; }
.session-row { display: flex; align-items: center; gap: 6px; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot-running { background: #22C55E; animation: pulse 1.5s infinite; }
.dot-idle { background: #D1D5DB; }
.dot-error { background: #EF4444; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
.session-title { font-size: 13px; font-weight: 500; color: #1E1B3A; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1; }
.session-meta { font-size: 11px; color: #94A3B8; padding-left: 14px; }
.session-empty { color: #94A3B8; font-size: 13px; padding: 12px 0; text-align: center; }

/* Action buttons */
.action-btns { display: flex; gap: 2px; opacity: 0; transition: opacity 0.15s; flex-shrink: 0; }
.project-row:hover .action-btns,
.session-item:hover .action-btns { opacity: 1; }
.btn-icon { background: none; border: none; cursor: pointer; font-size: 12px; width: 20px; height: 20px; border-radius: 4px; display: flex; align-items: center; justify-content: center; }
.btn-close { color: #94A3B8; }
.btn-close:hover { color: #64748B; background: #E2E6EC; }
.btn-delete { color: #94A3B8; }
.btn-delete:hover { color: #EF4444; background: #FEE2E2; }
.session-action-btns { margin-left: auto; }
</style>
