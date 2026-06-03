import { ref } from 'vue';
import { defineStore } from 'pinia';

interface DebugEntry {
  prefix: string;
  message: string;
  color: string;
  groupKey?: string;
  groupIdx?: number;
  opacity: number;
  data?: any;
}

export const useDebugStore = defineStore('debug', () => {
  const entries = ref<DebugEntry[]>([]);
  const usageProgress = ref(0);
  const usageText = ref('-- tokens');
  const open = ref(false);

  function addEvent(prefix: string, message: string, color: string, data?: any, groupKey?: string) {
    entries.value.push({ prefix, message, color, groupKey, opacity: 1.0, data });
    if (entries.value.length > 100) entries.value = entries.value.slice(-100);
  }

  function updateUsage(tokens: number, maxTokens: number) {
    usageProgress.value = Math.min(tokens / maxTokens, 1.0);
    usageText.value = `~${tokens} tokens (${Math.round(usageProgress.value * 100)}%)`;
  }

  function clear() { entries.value = []; }

  return { entries, usageProgress, usageText, open, addEvent, updateUsage, clear };
});
