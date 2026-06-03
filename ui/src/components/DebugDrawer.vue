<template>
  <div class="debug-drawer">
    <div class="debug-header">
      <span class="debug-title">调试面板</span>
      <button class="debug-close" @click="debugStore.open = false">&times;</button>
    </div>
    <div class="usage-section">
      <div class="usage-label">上下文窗口</div>
      <div class="progress-bar"><div class="progress-fill" :style="{ width: (debugStore.usageProgress * 100) + '%' }"></div></div>
      <div class="usage-text">{{ debugStore.usageText }}</div>
    </div>
    <div class="event-log">
      <div v-for="(entry, i) in debugStore.entries" :key="i" class="event-entry" :style="{ opacity: entry.opacity }" @click="showData(entry)">
        <span class="event-prefix" :style="{ color: entry.color }">{{ entry.prefix }}</span>
        <span class="event-message">{{ entry.message }}</span>
      </div>
    </div>
    <div class="debug-footer">
      <button class="btn-clear" @click="debugStore.clear()">Clear</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useDebugStore } from '../stores/debug';
const debugStore = useDebugStore();

function showData(entry: { data?: any }) {
  if (entry.data) {
    window.alert(JSON.stringify(entry.data, null, 2));
  }
}
</script>

<style scoped>
.debug-drawer { width: 280px; border-left: 1px solid #F1F3F6; background: #FAFBFC; display: flex; flex-direction: column; padding: 12px; }
.debug-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.debug-title { font-size: 15px; font-weight: 600; color: #1E1B3A; }
.debug-close { background: none; border: none; font-size: 16px; color: #64748B; cursor: pointer; padding: 2px 6px; }
.usage-section { margin-bottom: 10px; }
.usage-label { font-size: 13px; color: #64748B; margin-bottom: 4px; }
.progress-bar { height: 6px; background: #E8E8EF; border-radius: 3px; }
.progress-fill { height: 100%; background: #6366F1; border-radius: 3px; transition: width 0.3s; }
.usage-text { font-size: 13px; color: #64748B; margin-top: 2px; }
.event-log { flex: 1; overflow-y: auto; background: #F8F9FB; border-radius: 6px; padding: 6px; border: 1px solid #EEF0F4; }
.event-entry { padding: 3px 4px; border-bottom: 1px solid #E8EAF0; cursor: default; font-size: 13px; line-height: 1.4; }
.event-prefix { font-weight: 600; margin-right: 4px; }
.debug-footer { margin-top: 8px; }
.btn-clear { font-size: 13px; color: #EF4444; background: none; border: none; cursor: pointer; }
</style>
