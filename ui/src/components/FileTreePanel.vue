<template>
  <div class="flex flex-col h-full bg-surface-1 border-r border-border-default select-none relative" :style="{ width: panelWidth + 'px', minWidth: '200px', maxWidth: '400px' }">
    <!-- Tab bar -->
    <div class="flex items-center border-b border-border-default bg-surface-2 text-xs overflow-x-auto shrink-0">
      <button
        class="px-3 py-1.5 border-b-2 whitespace-nowrap cursor-pointer transition-colors bg-transparent border-x-0 border-t-0"
        :class="fileBrowser.activeTab === 'tree' ? 'border-accent text-text-primary' : 'border-transparent text-text-muted hover:text-text-secondary'"
        @click="fileBrowser.activeTab = 'tree'"
      >文件树</button>
      <button
        v-if="fileBrowser.previewPath"
        class="px-3 py-1.5 border-b-2 whitespace-nowrap cursor-pointer transition-colors flex items-center gap-1 bg-transparent border-x-0 border-t-0"
        :class="fileBrowser.activeTab === fileBrowser.previewPath ? 'border-accent text-text-primary' : 'border-transparent text-text-muted hover:text-text-secondary'"
        @click="fileBrowser.activeTab = fileBrowser.previewPath!"
      >
        <span class="font-mono truncate max-w-[100px]">{{ fileName(fileBrowser.previewPath) }}</span>
        <span class="text-text-muted hover:text-text-primary" @click.stop="fileBrowser.closePreview()">✕</span>
      </button>
    </div>

    <!-- File tree view -->
    <div v-show="fileBrowser.activeTab === 'tree'" class="flex flex-col flex-1 overflow-hidden">
      <!-- Search box -->
      <div class="px-2 py-1.5 border-b border-border-subtle shrink-0">
        <input
          v-model="searchInput"
          class="w-full bg-surface-0 border border-border-default rounded px-2 py-1 text-xs text-text-primary outline-none focus:border-accent"
          placeholder="搜索文件..."
          @input="onSearchInput"
        />
      </div>

      <!-- Search results -->
      <div v-if="searchInput && fileBrowser.searchResults.length > 0" class="flex-1 overflow-y-auto py-1">
        <div
          v-for="item in fileBrowser.searchResults"
          :key="item.path"
          class="flex items-center gap-1.5 px-3 py-1 cursor-pointer text-xs hover:bg-surface-2"
          :class="fileBrowser.selectedFile === item.path ? 'bg-accent-subtle text-accent' : 'text-text-secondary'"
          @click="onFileClick(item)"
          @dblclick="onFileDblClick(item)"
        >
          <span class="shrink-0">{{ fileIcon(item.name) }}</span>
          <span class="truncate font-mono">{{ item.name }}</span>
          <span class="ml-auto text-text-muted truncate max-w-[80px]">{{ item.path }}</span>
        </div>
      </div>

      <!-- Empty search -->
      <div v-else-if="searchInput && fileBrowser.searchResults.length === 0" class="flex-1 flex items-center justify-center text-text-muted text-xs py-8">
        无搜索结果
      </div>

      <!-- Tree -->
      <div v-else class="flex-1 overflow-y-auto py-1">
        <div v-if="fileBrowser.tree.length === 0 && !fileBrowser.loading" class="flex items-center justify-center text-text-muted text-xs py-8">
          暂无文件
        </div>
        <template v-for="node in fileBrowser.tree" :key="node.path">
          <TreeNodeItem
            :node="node"
            :depth="0"
            :selected="fileBrowser.selectedFile"
            :expanded="fileBrowser.expandedDirs.has(node.path)"
            @select="onFileClick"
            @dblclick="onFileDblClick"
          />
        </template>
      </div>
    </div>

    <!-- Preview view -->
    <div v-show="fileBrowser.activeTab !== 'tree' && fileBrowser.previewPath" class="flex flex-col flex-1 overflow-hidden">
      <div class="px-2 py-1 text-[10px] text-text-muted border-b border-border-subtle truncate shrink-0">
        {{ fileBrowser.previewPath }}
      </div>
      <div class="flex-1 overflow-auto p-2">
        <div v-if="fileBrowser.error" class="text-xs text-danger p-2">{{ fileBrowser.error }}</div>
        <pre v-else class="font-mono text-[11px] leading-relaxed text-text-primary whitespace-pre-wrap break-all">{{ fileBrowser.previewContent }}</pre>
      </div>
      <div class="flex gap-1.5 px-2 py-1.5 border-t border-border-default shrink-0">
        <button class="bg-accent text-white text-xs px-3 py-1 rounded cursor-pointer hover:bg-accent-hover border-none" @click="sendToAgent">→ Agent</button>
        <button class="bg-surface-3 text-text-secondary text-xs px-3 py-1 rounded cursor-pointer hover:bg-surface-4 border-none" @click="openInEditor">⛶ 展开</button>
      </div>
    </div>

    <!-- Resize handle -->
    <div
      class="absolute top-0 right-0 w-1 h-full cursor-col-resize hover:bg-accent/30"
      @mousedown.prevent="startResize"
    ></div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useFileBrowserStore, type TreeNode } from '../stores/fileBrowser';
import { useChatStore } from '../stores/chat';
import TreeNodeItem from './TreeNodeItem.vue';

const fileBrowser = useFileBrowserStore();
const chatStore = useChatStore();

const panelWidth = ref(260);
const searchInput = ref('');
let searchTimer: ReturnType<typeof setTimeout> | null = null;

function fileName(path: string) {
  return path.split('/').pop() || path;
}

function fileIcon(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase() || '';
  const icons: Record<string, string> = {
    py: '🐍', ts: '🔷', js: '🔷', vue: '💚', html: '🌐', css: '🎨',
    json: '📋', md: '📝', yaml: '📋', yml: '📋', toml: '📋',
    rs: '🦀', go: '🔵', java: '☕', sh: '⚙️', bat: '⚙️',
    txt: '📄', sql: '🗃️', xml: '🌐',
  };
  return icons[ext] || '📄';
}

function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    fileBrowser.searchFiles(searchInput.value);
  }, 300);
}

function onFileClick(node: TreeNode) {
  if (node.type === 'dir') {
    if (fileBrowser.expandedDirs.has(node.path)) {
      fileBrowser.expandedDirs.delete(node.path);
    } else {
      if (!node.loaded) {
        fileBrowser.loadDir(node.path);
      } else {
        fileBrowser.expandedDirs = new Set([...fileBrowser.expandedDirs, node.path]);
      }
    }
  } else {
    fileBrowser.selectFile(node.path);
  }
}

function onFileDblClick(node: TreeNode) {
  if (node.type === 'file') {
    fileBrowser.openEditor(node.path);
  }
}

function sendToAgent() {
  if (fileBrowser.previewPath) {
    chatStore.insertToInput(`@file:${fileBrowser.previewPath}`);
  }
}

function openInEditor() {
  if (fileBrowser.previewPath) {
    fileBrowser.openEditor(fileBrowser.previewPath);
  }
}

function startResize(e: MouseEvent) {
  const startX = e.clientX;
  const startWidth = panelWidth.value;
  function onMove(ev: MouseEvent) {
    panelWidth.value = Math.min(400, Math.max(200, startWidth + (ev.clientX - startX)));
  }
  function onUp() {
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
  }
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
}
</script>
