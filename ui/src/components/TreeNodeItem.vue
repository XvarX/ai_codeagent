<template>
  <div>
    <div
      class="flex items-center gap-1 cursor-pointer text-xs py-0.5 pr-2 transition-colors"
      :style="{ paddingLeft: depth * 14 + 8 + 'px' }"
      :class="node.type === 'file' && selected === node.path ? 'bg-accent-subtle text-accent' : 'text-text-secondary hover:bg-surface-2'"
      @click="$emit('select', node)"
      @dblclick="$emit('dblclick', node)"
    >
      <span v-if="node.type === 'dir'" class="shrink-0 w-3 text-center text-text-muted">
        {{ expanded ? '▾' : '▸' }}
      </span>
      <span v-else class="shrink-0 w-3"></span>
      <span class="shrink-0">{{ node.type === 'dir' ? (expanded ? '📂' : '📁') : fileIcon(node.name) }}</span>
      <span class="truncate font-mono">{{ node.name }}</span>
    </div>
    <div v-if="node.type === 'dir' && expanded && node.children">
      <div v-if="!node.loaded" class="text-text-muted text-[10px] pl-4 py-0.5">Loading...</div>
      <TreeNodeItem
        v-for="child in node.children"
        :key="child.path"
        :node="child"
        :depth="depth + 1"
        :selected="selected"
        :expanded="expandedDirs.has(child.path)"
        @select="$emit('select', $event)"
        @dblclick="$emit('dblclick', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { TreeNode } from '../stores/fileBrowser';

const props = defineProps<{
  node: TreeNode;
  depth: number;
  selected: string | null;
  expanded: boolean;
}>();

defineEmits<{
  select: [node: TreeNode];
  dblclick: [node: TreeNode];
}>();

import { useFileBrowserStore } from '../stores/fileBrowser';
const fileBrowser = useFileBrowserStore();
const expandedDirs = fileBrowser.expandedDirs;

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
</script>
