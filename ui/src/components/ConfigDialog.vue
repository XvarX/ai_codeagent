<template>
  <Teleport to="body">
    <div class="dialog-overlay" @click.self="onCancel">
      <div class="dialog">
        <h3>配置</h3>

        <!-- Provider dropdown -->
        <label class="field">
          Provider
          <select v-model="provider" class="input select-input">
            <option v-for="p in providerList" :key="p" :value="p">{{ p }}</option>
          </select>
        </label>

        <label class="field">
          Model
          <input v-model="model" class="input" placeholder="claude-sonnet-4-6-20250514" />
        </label>

        <label class="field">
          API Key
          <input v-model="apiKey" type="password" class="input" placeholder="Enter API key" />
        </label>

        <label class="field">
          Base URL
          <input v-model="baseUrl" class="input" placeholder="https://api.anthropic.com" />
        </label>

        <!-- Custom Provider -->
        <div class="section">
          <div class="section-header" @click="showAddProvider = !showAddProvider">
            <span>自定义 Provider</span>
            <span class="chevron" v-html="showAddProvider ? '&#9660;' : '&#9654;'"></span>
          </div>
          <div v-if="showAddProvider" class="section-body">
            <div class="add-provider-row">
              <input v-model="newProviderName" class="input" placeholder="名称" />
              <select v-model="newProviderType" class="input select-input" style="width: 110px; flex-shrink: 0;">
                <option v-for="t in builtinProviders" :key="t" :value="t">{{ t }}</option>
              </select>
              <button class="btn-add" @click="addCustomProvider" :disabled="!newProviderName.trim()">添加</button>
            </div>
            <div v-if="customProviders.length" class="custom-list">
              <div v-for="(cp, i) in customProviders" :key="i" class="custom-item">
                <span class="custom-name">{{ cp.name }}</span>
                <span class="custom-type">({{ cp.type }})</span>
                <button class="btn-remove" @click="removeCustomProvider(i)">&times;</button>
              </div>
            </div>
            <p v-else class="placeholder-text">暂无自定义 Provider</p>
          </div>
        </div>

        <!-- Advanced Settings -->
        <div class="section">
          <div class="section-header" @click="showAdvanced = !showAdvanced">
            <span>高级设置</span>
            <span class="chevron" v-html="showAdvanced ? '&#9660;' : '&#9654;'"></span>
          </div>
          <div v-if="showAdvanced" class="section-body">
            <label class="field">
              Context Window
              <input v-model.number="contextWindow" type="number" class="input" min="1000" step="1000" />
            </label>
            <label class="field">
              Compact Threshold
              <input v-model.number="compactThreshold" type="number" class="input" min="0.1" max="1.0" step="0.05" />
              <span class="field-hint">范围: 0.1 ~ 1.0</span>
            </label>
            <label class="field">
              Reserved Output
              <input v-model.number="reservedOutput" type="number" class="input" min="1000" step="500" />
            </label>
          </div>
        </div>

        <!-- Delete provider -->
        <div v-if="!confirmDelete" class="delete-section">
          <button v-if="isBuiltinProvider" class="btn-danger btn-disabled" disabled>内置 Provider 不可删除</button>
          <button v-else class="btn-danger" @click="confirmDelete = true">删除当前 Provider</button>
        </div>
        <div v-else class="delete-section confirm-delete">
          <span class="confirm-text">确认删除 "{{ provider }}"？</span>
          <div class="confirm-actions">
            <button class="btn-save btn-danger-bg" @click="deleteProvider">确认</button>
            <button class="btn-cancel" @click="confirmDelete = false">取消</button>
          </div>
        </div>

        <p v-if="saved" class="saved-msg">已保存!</p>

        <div class="dialog-actions">
          <button class="btn-save" @click="save">保存</button>
          <button class="btn-cancel" @click="onCancel">取消</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
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

const providerList = computed(() => [
  ...builtinProviders,
  ...customProviders.value.map(cp => cp.name),
]);

// --- Form state ---
const defaultProvider = computed(() => {
  const storeVal = agentStore.provider;
  if (storeVal && providerList.value.includes(storeVal)) return storeVal;
  return 'anthropic';
});

const provider = ref(defaultProvider.value);
const model = ref(agentStore.model || '');
const apiKey = ref('');
const baseUrl = ref('');

// Advanced settings
const contextWindow = ref(128000);
const compactThreshold = ref(0.85);
const reservedOutput = ref(8000);

// UI state
const showAdvanced = ref(false);
const showAddProvider = ref(false);
const newProviderName = ref('');
const newProviderType = ref<string>('openai');
const confirmDelete = ref(false);
const saved = ref(false);

// --- Computed ---
const isBuiltinProvider = computed(() => builtinProviders.includes(provider.value as any));

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

<style scoped>
/* ---- overlay & dialog ---- */
.dialog-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; z-index: 100; }
.dialog { background: white; border-radius: 12px; padding: 24px; min-width: 420px; max-width: 520px; box-shadow: 0 4px 24px rgba(0,0,0,0.12); max-height: 90vh; overflow-y: auto; }
.dialog h3 { margin-bottom: 16px; font-size: 17px; color: #1E1B3A; }

/* ---- fields ---- */
.field { display: block; margin-bottom: 12px; font-size: 14px; color: #64748B; }
.input { display: block; width: 100%; padding: 7px 10px; border: 1px solid #E2E6EC; border-radius: 6px; font-size: 15px; margin-top: 4px; outline: none; box-sizing: border-box; }
.input:focus { border-color: #6366F1; }
.select-input { appearance: auto; background: white; cursor: pointer; }
.field-hint { display: block; font-size: 12px; color: #94A3B8; margin-top: 2px; }

/* ---- collapsible sections ---- */
.section { border-top: 1px solid #EEF0F4; margin-top: 12px; padding-top: 12px; }
.section-header { display: flex; justify-content: space-between; align-items: center; cursor: pointer; font-size: 14px; font-weight: 600; color: #1E1B3A; user-select: none; }
.section-header:hover { color: #6366F1; }
.chevron { font-size: 12px; color: #94A3B8; }
.section-body { padding-top: 10px; }

/* ---- custom provider ---- */
.add-provider-row { display: flex; gap: 6px; align-items: flex-start; }
.add-provider-row .input { margin-top: 0; }
.btn-add { padding: 7px 12px; border: none; border-radius: 6px; background: #6366F1; color: white; cursor: pointer; font-size: 13px; white-space: nowrap; flex-shrink: 0; }
.btn-add:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-add:hover:not(:disabled) { background: #5558E8; }
.custom-list { margin-top: 8px; }
.custom-item { display: flex; align-items: center; gap: 6px; padding: 5px 8px; border: 1px solid #EEF0F4; border-radius: 6px; margin-bottom: 4px; font-size: 14px; color: #1E1B3A; }
.custom-name { font-weight: 500; }
.custom-type { color: #94A3B8; font-size: 12px; }
.btn-remove { margin-left: auto; background: none; border: none; color: #EF4444; cursor: pointer; font-size: 16px; line-height: 1; padding: 0 4px; }
.btn-remove:hover { color: #DC2626; }
.placeholder-text { color: #94A3B8; font-size: 13px; margin-top: 8px; }

/* ---- delete section ---- */
.delete-section { border-top: 1px solid #EEF0F4; margin-top: 12px; padding-top: 12px; }
.btn-danger { padding: 6px 14px; border: 1px solid #FECACA; border-radius: 6px; background: #FEF2F2; color: #EF4444; cursor: pointer; font-size: 13px; }
.btn-danger:hover:not(:disabled) { background: #FEE2E2; }
.btn-danger.btn-disabled { opacity: 0.5; cursor: not-allowed; border-color: #E2E6EC; color: #94A3B8; background: #FAFBFC; }
.confirm-delete { display: flex; flex-direction: column; gap: 8px; }
.confirm-text { font-size: 14px; color: #EF4444; font-weight: 500; }
.confirm-actions { display: flex; gap: 6px; }
.btn-danger-bg { background: #EF4444 !important; }
.btn-danger-bg:hover { background: #DC2626 !important; }

/* ---- save feedback ---- */
.saved-msg { color: #22C55E; font-size: 14px; margin-bottom: 8px; }

/* ---- dialog buttons ---- */
.dialog-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
.btn-save { padding: 7px 18px; border: none; border-radius: 6px; background: #6366F1; color: white; cursor: pointer; font-size: 14px; }
.btn-save:hover { background: #5558E8; }
.btn-cancel { padding: 7px 18px; border: 1px solid #E2E6EC; border-radius: 6px; background: white; cursor: pointer; font-size: 14px; }
.btn-cancel:hover { background: #FAFBFC; }
</style>
