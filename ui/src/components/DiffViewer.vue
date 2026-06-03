<template>
  <div class="diff-viewer">
    <div class="diff-header" @click="open = !open">
      <span class="arrow">{{ open ? '▼' : '▶' }}</span>
      <span class="filename">{{ filename }}</span>
      <span class="summary">+{{ added }} -{{ removed }}</span>
    </div>
    <div v-if="open" class="diff-body">
      <div class="diff-placeholder">Diff viewer — will be implemented with js diff library</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';

const props = defineProps<{ filePath: string; oldContent: string; newContent: string }>();
const open = ref(true);
const filename = computed(() => props.filePath.replace(/\\/g, '/').split('/').pop() || '');
const added = ref(0);
const removed = ref(0);
</script>

<style scoped>
.diff-viewer { border: 1px solid #E2E8F0; border-radius: 8px; overflow: hidden; margin: 8px 0; }
.diff-header { display: flex; align-items: center; gap: 6px; padding: 8px 10px; background: #F8F9FB; cursor: pointer; }
.arrow { font-size: 12px; color: #6366F1; }
.filename { font-size: 16px; font-weight: 600; color: #1E1B3A; }
.summary { font-family: Consolas, monospace; font-size: 15px; color: #64748B; background: #F1F5F9; padding: 1px 6px; border-radius: 4px; }
.diff-body { border-top: 1px solid #E2E8F0; }
.diff-placeholder { padding: 12px; color: #94A3B8; font-size: 14px; text-align: center; }
</style>
