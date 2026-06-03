import { ref } from 'vue';
import { defineStore } from 'pinia';

export interface DebugEntry {
  id: number;
  prefix: string;
  message: string;
  color: string;
  data?: any;
  groupKey?: string;
  groupIdx?: number | null;
  opacity: number;
}

export const useDebugStore = defineStore('debug', () => {
  const entries = ref<DebugEntry[]>([]);
  const usageProgress = ref(0);
  const usageText = ref('-- tokens');
  const usageTokens = ref(0);
  const maxTokens = ref(128000);
  const compacting = ref(false);
  const open = ref(false);

  let _nextId = 1;

  function addEvent(
    prefix: string,
    message: string,
    color: string,
    data?: any,
    groupKey?: string,
  ) {
    const id = _nextId++;
    const entry: DebugEntry = {
      id,
      prefix,
      message,
      color,
      data,
      groupKey,
      groupIdx: null,
      opacity: 1.0,
    };
    entries.value.push(entry);
    if (entries.value.length > 100) {
      entries.value = entries.value.slice(-100);
    }
  }

  function updateContextUsage(tokens: number, max: number = 128000) {
    usageTokens.value = tokens;
    maxTokens.value = max;
    const pct = Math.min(tokens / Math.max(max, 1), 1.0);
    usageProgress.value = pct;
    usageText.value = `~${tokens.toLocaleString()} tokens (${Math.round(pct * 100)}%)`;
  }

  function clear() {
    entries.value = [];
  }

  function setCompacting(busy: boolean) {
    compacting.value = busy;
  }

  return {
    entries,
    usageProgress,
    usageText,
    usageTokens,
    maxTokens,
    compacting,
    open,
    addEvent,
    updateContextUsage,
    clear,
    setCompacting,
  };
});
