<template>
  <div class="debug-drawer">
    <!-- Header -->
    <div class="debug-header">
      <span class="debug-title">调试面板</span>
      <button class="debug-close" @click="debugStore.open = false">&times;</button>
    </div>

    <!-- Context Usage -->
    <div class="usage-section">
      <div class="usage-label">上下文窗口</div>
      <div class="progress-bar">
        <div
          class="progress-fill"
          :style="{ width: (debugStore.usageProgress * 100) + '%' }"
        ></div>
      </div>
      <div class="usage-text">{{ debugStore.usageText }}</div>
    </div>

    <!-- Event Log -->
    <div class="event-log">
      <div
        v-for="entry in debugStore.entries"
        :key="entry.id"
        class="event-entry"
        :class="{ 'event-entry--clickable': entry.data }"
        :style="{ opacity: entry.opacity }"
        @click="onEntryClick(entry)"
      >
        <span class="event-prefix" :style="{ color: entry.color }">{{ entry.prefix }}</span>
        <span class="event-message">{{ entry.message }}</span>
      </div>
      <div v-if="debugStore.entries.length === 0" class="event-empty">
        暂无事件
      </div>
    </div>

    <!-- Footer -->
    <div class="debug-footer">
      <button class="btn-clear" @click="debugStore.clear()">Clear History</button>
    </div>

    <!-- Detail Dialog (modal) -->
    <Teleport to="body">
      <div v-if="activeEntry" class="detail-overlay" @click.self="closeDetail">
        <div class="detail-dialog">
          <div class="detail-header">
            <span class="detail-title">{{ detailTitle }}</span>
            <button class="detail-close" @click="closeDetail">&times;</button>
          </div>
          <div class="detail-body">
            <pre class="detail-text">{{ detailText }}</pre>
          </div>
          <div class="detail-footer">
            <button class="detail-toggle" @click="toggleRaw">
              {{ showRaw ? 'Formatted' : 'Raw JSON' }}
            </button>
            <button class="detail-btn-close" @click="closeDetail">关闭</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useDebugStore, type DebugEntry } from '../stores/debug';

const debugStore = useDebugStore();

const activeEntry = ref<DebugEntry | null>(null);
const showRaw = ref(false);

const detailTitle = computed(() => {
  if (!activeEntry.value) return '';
  const data = activeEntry.value.data;
  if (data && typeof data === 'object' && data.type) {
    return data.type;
  }
  return activeEntry.value.prefix;
});

const detailText = computed(() => {
  if (!activeEntry.value) return '';
  const data = activeEntry.value.data;
  if (!data || typeof data !== 'object') return '';

  if (showRaw.value) {
    if (data.raw_json) return data.raw_json;
    try {
      return JSON.stringify(data, null, 2);
    } catch {
      return String(data);
    }
  }

  if (data.formatted) return data.formatted;

  // Fallback: build a readable representation
  const lines: string[] = [];
  lines.push(`Event: ${data.type || activeEntry.value!.prefix}`);
  lines.push('');
  for (const [k, v] of Object.entries(data)) {
    if (k === 'type' || k === 'formatted' || k === 'raw_json') continue;
    const valStr = typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v);
    if (valStr.length > 500) {
      lines.push(`${k}: ${valStr.slice(0, 500)}...`);
    } else {
      lines.push(`${k}: ${valStr}`);
    }
  }
  return lines.join('\n');
});

function onEntryClick(entry: DebugEntry) {
  if (!entry.data) return;
  activeEntry.value = entry;
  showRaw.value = false;
}

function closeDetail() {
  activeEntry.value = null;
  showRaw.value = false;
}

function toggleRaw() {
  showRaw.value = !showRaw.value;
}
</script>

<style scoped>
.debug-drawer {
  width: 280px;
  min-width: 280px;
  border-left: 1px solid #F1F3F6;
  background: #FAFBFC;
  display: flex;
  flex-direction: column;
  padding: 12px;
  height: 100%;
}

/* Header */
.debug-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.debug-title {
  font-size: 15px;
  font-weight: 600;
  color: #1E1B3A;
}
.debug-close {
  background: none;
  border: none;
  font-size: 20px;
  color: #64748B;
  cursor: pointer;
  padding: 2px 6px;
  line-height: 1;
}
.debug-close:hover {
  color: #EF4444;
}

/* Usage section */
.usage-section {
  margin-bottom: 10px;
}
.usage-label {
  font-size: 13px;
  color: #64748B;
  margin-bottom: 4px;
}
.progress-bar {
  height: 6px;
  background: #E8E8EF;
  border-radius: 3px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: #6366F1;
  border-radius: 3px;
  transition: width 0.3s ease;
}
.usage-text {
  font-size: 13px;
  color: #64748B;
  margin-top: 2px;
}

/* Event log */
.event-log {
  flex: 1;
  overflow-y: auto;
  background: #F8F9FB;
  border-radius: 6px;
  padding: 6px;
  border: 1px solid #EEF0F4;
  min-height: 0;
}
.event-entry {
  padding: 3px 4px;
  border-bottom: 1px solid #E8EAF0;
  font-size: 13px;
  line-height: 1.4;
  cursor: default;
  word-break: break-all;
}
.event-entry--clickable {
  cursor: pointer;
}
.event-entry--clickable:hover {
  background: #EEF0F4;
}
.event-prefix {
  font-weight: 600;
  margin-right: 4px;
}
.event-message {
  color: #64748B;
}
.event-empty {
  text-align: center;
  color: #94A3B8;
  font-size: 13px;
  padding: 16px 0;
}

/* Footer */
.debug-footer {
  margin-top: 8px;
}
.btn-clear {
  font-size: 13px;
  color: #EF4444;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
}
.btn-clear:hover {
  text-decoration: underline;
}

/* Detail Dialog (modal) */
.detail-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.detail-dialog {
  background: #FFFFFF;
  border-radius: 12px;
  width: 560px;
  max-width: 90vw;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.18);
}
.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 18px;
  border-bottom: 1px solid #EEF0F4;
}
.detail-title {
  font-size: 16px;
  font-weight: 600;
  color: #1E1B3A;
}
.detail-close {
  background: none;
  border: none;
  font-size: 22px;
  color: #64748B;
  cursor: pointer;
  padding: 2px 6px;
  line-height: 1;
}
.detail-close:hover {
  color: #EF4444;
}
.detail-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px 18px;
  min-height: 0;
}
.detail-text {
  font-family: 'Cascadia Code', 'Fira Code', 'JetBrains Mono', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.5;
  color: #334155;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
.detail-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 18px;
  border-top: 1px solid #EEF0F4;
}
.detail-toggle {
  font-size: 13px;
  color: #6366F1;
  background: none;
  border: 1px solid #E2E6EC;
  border-radius: 6px;
  padding: 6px 12px;
  cursor: pointer;
}
.detail-toggle:hover {
  background: #F0F0FF;
}
.detail-btn-close {
  font-size: 13px;
  color: #64748B;
  background: #F1F3F6;
  border: 1px solid #E2E6EC;
  border-radius: 6px;
  padding: 6px 14px;
  cursor: pointer;
}
.detail-btn-close:hover {
  background: #E2E6EC;
}
</style>
