<template>
  <div class="border-l border-border-default bg-surface-1 flex flex-col p-3 h-full relative" :style="collapsed ? { width: '36px', minWidth: '36px', padding: '4px' } : { width: drawerWidth + 'px', minWidth: drawerWidth + 'px' }">
    <!-- Resize handle -->
    <div class="absolute left-0 top-0 bottom-0 w-1 cursor-ew-resize z-10 hover:bg-accent/30" @mousedown="onResizeStart"></div>
    <template v-if="!collapsed">
      <!-- Header -->
      <div class="flex justify-between items-center mb-2">
        <button class="bg-transparent border-none cursor-pointer text-xs p-[2px_4px] text-text-secondary leading-none hover:text-text-primary" @click="collapsed = !collapsed">◀</button>
        <span class="text-[15px] font-semibold text-text-primary">调试面板</span>
        <button class="bg-transparent border-none text-xl text-text-secondary cursor-pointer py-0.5 px-[6px] leading-none hover:text-danger" @click="debugStore.open = false">&times;</button>
      </div>

      <!-- Context Usage -->
      <div class="mb-[10px]">
        <div class="text-[13px] text-text-secondary mb-1">上下文窗口</div>
        <div class="h-[6px] bg-surface-3 rounded-[3px] overflow-hidden">
          <div class="h-full bg-accent rounded-[3px] transition-[width] duration-300 ease" :style="{ width: (debugStore.usageProgress * 100) + '%' }"></div>
        </div>
        <div class="text-[13px] text-text-secondary mt-0.5">{{ debugStore.usageText }}</div>
      </div>

      <!-- Event Log -->
      <div class="flex-1 overflow-y-auto bg-surface-2 rounded-md p-[6px] border border-border-subtle min-h-0">
        <div
          v-for="entry in debugStore.entries"
          :key="entry.id"
          class="p-[4px_6px] border-b border-border-subtle text-[13px] leading-[1.4]"
          :class="entry.data ? 'cursor-pointer hover:bg-surface-3' : 'cursor-default'"
          :style="{ opacity: entry.opacity }"
          @click="onEntryClick(entry)"
        >
          <div class="font-semibold mb-0.5" :style="{ color: entry.color }">
            <span v-if="entry.opacity < 1.0" class="text-[11px] text-danger mr-[3px]">[Compacted]</span>
            {{ entry.prefix }}
            <span v-if="entry.groupIdx !== null" class="inline-block text-[11px] font-medium text-text-muted ml-1 bg-surface-2 rounded-[3px] px-1">G{{ entry.groupIdx }}</span>
          </div>
          <div class="text-text-secondary whitespace-pre-wrap break-all">{{ entry.message }}</div>
        </div>
        <div v-if="debugStore.entries.length === 0" class="text-center text-text-muted text-[13px] py-4">
          暂无事件
        </div>
      </div>

      <!-- Footer -->
      <div class="mt-2 flex gap-3 items-center">
        <button class="text-[13px] text-text-secondary bg-transparent border-none cursor-pointer p-0 disabled:text-accent-muted disabled:cursor-default hover:underline" @click="onCompact" :disabled="debugStore.compacting">{{ debugStore.compacting ? 'Compacting...' : 'Compact' }}</button>
        <button class="text-[13px] text-danger bg-transparent border-none cursor-pointer p-0 hover:underline" @click="debugStore.clear()">Clear History</button>
      </div>
    </template>
    <template v-else>
      <button class="bg-transparent border-none cursor-pointer text-xs p-[2px_4px] text-text-secondary leading-none hover:text-text-primary" @click="collapsed = !collapsed">▶</button>
      <div class="[writing-mode:vertical-lr] text-sm text-text-secondary text-center mt-2">调<br>试</div>
    </template>

    <!-- Detail Dialog (modal) -->
    <Teleport to="body">
      <div v-if="activeEntry" class="fixed inset-0 bg-black/40 flex items-center justify-center z-[1000]" @click.self="closeDetail">
        <div class="bg-surface-1 rounded-xl w-[560px] max-w-[90vw] max-h-[80vh] flex flex-col shadow-dialog">
          <div class="flex justify-between items-center p-[14px_18px] border-b border-border-subtle">
            <span class="text-base font-semibold text-text-primary">{{ detailTitle }}</span>
            <button class="bg-transparent border-none text-[22px] text-text-secondary cursor-pointer py-0.5 px-[6px] leading-none hover:text-danger" @click="closeDetail">&times;</button>
          </div>
          <div class="flex-1 overflow-y-auto p-[14px_18px] min-h-0">
            <pre class="font-mono text-[13px] leading-[1.5] text-text-primary whitespace-pre-wrap break-all m-0">{{ detailText }}</pre>
          </div>
          <div class="flex justify-end gap-2 p-[12px_18px] border-t border-border-subtle">
            <button class="text-[13px] text-accent bg-transparent border border-border-default rounded-md px-3 py-[6px] cursor-pointer hover:bg-accent-subtle" @click="toggleRaw">
              {{ showRaw ? 'Formatted' : 'Raw JSON' }}
            </button>
            <button class="text-[13px] text-text-secondary bg-surface-2 border border-border-default rounded-md px-[14px] py-[6px] cursor-pointer hover:bg-surface-3" @click="closeDetail">关闭</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useDebugStore, type DebugEntry } from '../stores/debug';
import { agentWs } from '../services/agentWs';

const debugStore = useDebugStore();
const collapsed = ref(false);

function onCompact() {
  debugStore.setCompacting(true);
  agentWs.send({ type: 'compact' });
}

const MIN_WIDTH = 200;
const MAX_WIDTH = 600;
const drawerWidth = ref(280);

const activeEntry = ref<DebugEntry | null>(null);
const showRaw = ref(false);

let resizing = false;

function onResizeStart(e: MouseEvent) {
  resizing = true;
  const startX = e.clientX;
  const startWidth = drawerWidth.value;

  function onMove(ev: MouseEvent) {
    if (!resizing) return;
    // Drag left = wider drawer (right edge stays, left edge moves left)
    const dx = startX - ev.clientX;
    drawerWidth.value = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth + dx));
  }

  function onUp() {
    resizing = false;
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }

  document.body.style.cursor = 'ew-resize';
  document.body.style.userSelect = 'none';
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
}

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
