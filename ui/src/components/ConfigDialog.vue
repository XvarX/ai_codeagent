<template>
  <Teleport to="body">
    <div class="fixed inset-0 bg-black/50 flex items-center justify-center z-[100]" @click.self="onCancel">
      <div class="bg-surface-1 rounded-xl p-6 min-w-[420px] max-w-[520px] max-h-[90vh] overflow-y-auto shadow-dialog">
        <h3 class="mb-4 text-[17px] font-semibold text-text-primary">配置</h3>

        <label class="block mb-3 text-sm text-text-secondary">
          Provider
          <select v-model="provider" @change="onProviderChange" class="block w-full p-[7px_10px] border border-border-default rounded-md text-sm bg-surface-2 text-text-primary outline-none focus:border-accent mt-1 cursor-pointer">
            <option v-for="p in providerList" :key="p" :value="p">{{ p }}</option>
          </select>
        </label>

        <label class="block mb-3 text-sm text-text-secondary">
          Model
          <input v-model="model" class="block w-full p-[7px_10px] border border-border-default rounded-md text-sm bg-surface-2 text-text-primary outline-none focus:border-accent mt-1 placeholder:text-text-muted" placeholder="claude-sonnet-4-6-20250514" />
        </label>

        <label class="block mb-3 text-sm text-text-secondary">
          API Key
          <div class="flex mt-1 gap-0">
            <input v-model="apiKey" :type="showKey ? 'text' : 'password'" class="flex-1 p-[7px_10px] border border-border-default rounded-l-md text-sm bg-surface-2 text-text-primary outline-none focus:border-accent placeholder:text-text-muted" placeholder="Enter API key" />
            <button class="px-2 py-[6px] border border-l-0 border-border-default rounded-r-md bg-surface-2 cursor-pointer text-sm leading-none hover:bg-surface-3 text-text-secondary" @click="showKey = !showKey" :title="showKey ? '隐藏' : '显示'">{{ showKey ? '🙈' : '👁' }}</button>
          </div>
        </label>

        <label class="block mb-3 text-sm text-text-secondary">
          Base URL
          <input v-model="baseUrl" class="block w-full p-[7px_10px] border border-border-default rounded-md text-sm bg-surface-2 text-text-primary outline-none focus:border-accent mt-1 placeholder:text-text-muted" placeholder="https://api.anthropic.com" />
        </label>

        <div class="border-t border-border-subtle mt-3 pt-3">
          <div class="flex justify-between items-center cursor-pointer select-none text-sm font-semibold text-text-primary hover:text-accent" @click="showAddProvider = !showAddProvider">
            <span>自定义 Provider</span>
            <span class="text-xs text-text-muted" v-html="showAddProvider ? '&#9660;' : '&#9654;'"></span>
          </div>
          <div v-if="showAddProvider" class="pt-[10px]">
            <div class="flex gap-[6px] items-start">
              <input v-model="newProviderName" class="flex-1 p-[7px_10px] border border-border-default rounded-md text-sm bg-surface-2 text-text-primary outline-none focus:border-accent placeholder:text-text-muted" placeholder="名称" />
              <select v-model="newProviderType" class="w-[110px] flex-shrink-0 p-[7px_10px] border border-border-default rounded-md text-sm bg-surface-2 text-text-primary outline-none focus:border-accent cursor-pointer">
                <option v-for="t in builtinProviders" :key="t" :value="t">{{ t }}</option>
              </select>
              <button class="px-3 py-[7px] border-none rounded-md bg-accent text-white cursor-pointer text-[13px] whitespace-nowrap flex-shrink-0 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-accent-hover" @click="addCustomProvider" :disabled="!newProviderName.trim()">添加</button>
            </div>
            <div v-if="customProviders.length" class="mt-2">
              <div v-for="(cp, i) in customProviders" :key="i" class="flex items-center gap-[6px] p-[5px_8px] border border-border-subtle rounded-md mb-1 text-sm text-text-primary">
                <span class="font-medium">{{ cp.name }}</span>
                <span class="text-text-muted text-xs">({{ cp.type }})</span>
                <button class="ml-auto bg-transparent border-none text-danger cursor-pointer text-base leading-none px-1 hover:opacity-70" @click="removeCustomProvider(i)">&times;</button>
              </div>
            </div>
            <p v-else class="text-text-muted text-[13px] mt-2">暂无自定义 Provider</p>
          </div>
        </div>

        <div class="border-t border-border-subtle mt-3 pt-3">
          <div class="flex justify-between items-center cursor-pointer select-none text-sm font-semibold text-text-primary hover:text-accent" @click="showAdvanced = !showAdvanced">
            <span>高级设置</span>
            <span class="text-xs text-text-muted" v-html="showAdvanced ? '&#9660;' : '&#9654;'"></span>
          </div>
          <div v-if="showAdvanced" class="pt-[10px]">
            <label class="block mb-3 text-sm text-text-secondary">
              Context Window
              <input v-model.number="contextWindow" type="number" class="block w-full p-[7px_10px] border border-border-default rounded-md text-sm bg-surface-2 text-text-primary outline-none focus:border-accent mt-1" min="1000" step="1000" />
            </label>
            <label class="block mb-3 text-sm text-text-secondary">
              Compact Threshold
              <input v-model.number="compactThreshold" type="number" class="block w-full p-[7px_10px] border border-border-default rounded-md text-sm bg-surface-2 text-text-primary outline-none focus:border-accent mt-1" min="0.1" max="1.0" step="0.05" />
              <span class="block text-xs text-text-muted mt-0.5">范围: 0.1 ~ 1.0</span>
            </label>
            <label class="block mb-3 text-sm text-text-secondary">
              Reserved Output
              <input v-model.number="reservedOutput" type="number" class="block w-full p-[7px_10px] border border-border-default rounded-md text-sm bg-surface-2 text-text-primary outline-none focus:border-accent mt-1" min="1000" step="500" />
            </label>
          </div>
        </div>

        <div class="border-t border-border-subtle mt-3 pt-3">
          <div v-if="!confirmDelete">
            <button v-if="isBuiltinProvider" class="px-[14px] py-[6px] border border-border-default rounded-md bg-surface-2 text-text-muted cursor-not-allowed text-[13px] opacity-60" disabled>内置 Provider 不可删除</button>
            <button v-else class="px-[14px] py-[6px] border border-danger/30 rounded-md bg-danger-subtle text-danger cursor-pointer text-[13px] hover:bg-danger-subtle/60" @click="confirmDelete = true">删除当前 Provider</button>
          </div>
          <div v-else class="flex flex-col gap-2">
            <span class="text-sm text-danger font-medium">确认删除 "{{ provider }}"？</span>
            <div class="flex gap-[6px]">
              <button class="px-[14px] py-[6px] border-none rounded-md bg-danger text-white cursor-pointer text-[13px] hover:opacity-85" @click="deleteProvider">确认</button>
              <button class="px-[14px] py-[6px] border border-border-default rounded-md bg-transparent text-text-primary cursor-pointer text-[13px] hover:bg-surface-2" @click="confirmDelete = false">取消</button>
            </div>
          </div>
        </div>

        <p v-if="saved" class="text-success text-sm my-2">已保存!</p>

        <div class="flex gap-2 justify-end mt-4">
          <button class="px-[18px] py-[7px] border-none rounded-md bg-accent text-white cursor-pointer text-sm hover:bg-accent-hover" @click="save">保存</button>
          <button class="px-[18px] py-[7px] border border-border-default rounded-md bg-transparent text-text-primary cursor-pointer text-sm hover:bg-surface-2" @click="onCancel">取消</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { agentWs } from '../services/agentWs';
import { useAgentStore } from '../stores/agent';

const emit = defineEmits<{ close: [] }>();
const agentStore = useAgentStore();

const STORAGE_KEY = 'customProviders';
const builtinProviders = ['anthropic', 'openai', 'glm', 'deepseek'] as const;

// --- Persistent custom providers from localStorage ---
function loadCustomProviders(): Array<{ name: string; type: string }> {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
  } catch {
    return [];
  }
}

function persistCustomProviders() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(customProviders.value));
}

const customProviders = ref<Array<{ name: string; type: string }>>(loadCustomProviders());

const providerList = computed(() => {
  const merged = new Set([...builtinProviders, ...allProviders.value, ...customProviders.value.map(cp => cp.name)]);
  return [...merged];
});

// --- Per-provider config cache from backend ---
const providerConfigs = ref<Record<string, any>>({});
const allProviders = ref<string[]>([...builtinProviders]);

// --- Form state ---
const provider = ref('anthropic');
const model = ref('');
const apiKey = ref('');
const baseUrl = ref('');
const contextWindow = ref(128000);
const compactThreshold = ref(0.85);
const reservedOutput = ref(8000);

// UI state
const showAdvanced = ref(false);
const showAddProvider = ref(false);
const newProviderName = ref('');
const newProviderType = ref<string>('openai');
const showKey = ref(false);
const confirmDelete = ref(false);
const saved = ref(false);

const isBuiltinProvider = computed(() => builtinProviders.includes(provider.value as any));

function applyProviderConfig(p: string) {
  const pc = providerConfigs.value[p] || {};
  model.value = pc.model || '';
  apiKey.value = pc.api_key || '';
  baseUrl.value = pc.base_url || '';
  contextWindow.value = pc.context_window || 128000;
  compactThreshold.value = pc.compact_threshold || 0.85;
  reservedOutput.value = pc.reserved_output || 8000;
}

function onProviderChange() {
  applyProviderConfig(provider.value);
}

function onConfigReceived(d: any) {
  // Store all per-provider configs from backend
  if (d.provider_configs) {
    providerConfigs.value = d.provider_configs;
  }
  if (d.providers) {
    allProviders.value = d.providers;
  }
  // Apply current provider's config
  const cur = agentStore.provider || d.provider || 'anthropic';
  provider.value = cur;
  applyProviderConfig(cur);
}

onMounted(() => {
  agentWs.on('config', onConfigReceived);
  agentWs.send({ type: 'get_config' });
});

onUnmounted(() => {
  agentWs.off('config', onConfigReceived);
});

// --- Methods ---
function addCustomProvider() {
  const name = newProviderName.value.trim();
  if (!name) return;
  if (builtinProviders.includes(name as any) || customProviders.value.some(cp => cp.name === name)) {
    return;
  }
  customProviders.value.push({ name, type: newProviderType.value });
  persistCustomProviders();
  newProviderName.value = '';
}

function removeCustomProvider(index: number) {
  const removed = customProviders.value[index];
  customProviders.value.splice(index, 1);
  persistCustomProviders();
  if (provider.value === removed.name) {
    provider.value = providerList.value[0];
  }
}

function deleteProvider() {
  const idx = customProviders.value.findIndex(cp => cp.name === provider.value);
  if (idx !== -1) {
    removeCustomProvider(idx);
  }
  confirmDelete.value = false;
}

function save() {
  agentWs.send({
    type: 'reconfigure',
    config: {
      provider: provider.value,
      model: model.value || undefined,
      api_key: apiKey.value || undefined,
      base_url: baseUrl.value || undefined,
      context_window: contextWindow.value || 128000,
      compact_threshold: compactThreshold.value || 0.85,
      reserved_output: reservedOutput.value || 8000,
    },
  });
  saved.value = true;
  setTimeout(() => {
    saved.value = false;
    emit('close');
  }, 600);
}

function onCancel() {
  confirmDelete.value = false;
  emit('close');
}
</script>
