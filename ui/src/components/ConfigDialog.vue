<template>
  <div class="dialog-overlay" @click.self="$emit('close')">
    <div class="dialog">
      <h3>配置</h3>
      <label class="field">Provider <input v-model="provider" class="input" placeholder="anthropic" /></label>
      <label class="field">Model <input v-model="model" class="input" placeholder="claude-sonnet-4-6-20250514" /></label>
      <label class="field">API Key <input v-model="apiKey" type="password" class="input" placeholder="••••" /></label>
      <label class="field">Base URL <input v-model="baseUrl" class="input" placeholder="https://api.anthropic.com" /></label>
      <p v-if="saved" class="saved-msg">Saved!</p>
      <div class="dialog-actions">
        <button class="btn-save" @click="save">Save</button>
        <button class="btn-cancel" @click="$emit('close')">Cancel</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { agentWs } from '../services/agentWs';
import { useAgentStore } from '../stores/agent';

const emit = defineEmits<{ close: [] }>();
const agentStore = useAgentStore();
const provider = ref(agentStore.provider);
const model = ref(agentStore.model);
const apiKey = ref('');
const baseUrl = ref('');
const saved = ref(false);

function save() {
  agentWs.send({
    type: 'reconfigure',
    config: {
      provider: provider.value,
      model: model.value,
      api_key: apiKey.value || undefined,
      base_url: baseUrl.value || undefined,
    },
  });
  saved.value = true;
  setTimeout(() => {
    saved.value = false;
    emit('close');
  }, 600);
}
</script>

<style scoped>
.dialog-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; z-index: 100; }
.dialog { background: white; border-radius: 12px; padding: 24px; min-width: 380px; box-shadow: 0 4px 24px rgba(0,0,0,0.12); }
.dialog h3 { margin-bottom: 16px; font-size: 17px; color: #1E1B3A; }
.field { display: block; margin-bottom: 12px; font-size: 14px; color: #64748B; }
.input { display: block; width: 100%; padding: 7px 10px; border: 1px solid #E2E6EC; border-radius: 6px; font-size: 15px; margin-top: 4px; outline: none; }
.input:focus { border-color: #6366F1; }
.saved-msg { color: #22C55E; font-size: 14px; margin-bottom: 8px; }
.dialog-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
.btn-save { padding: 7px 18px; border: none; border-radius: 6px; background: #6366F1; color: white; cursor: pointer; font-size: 14px; }
.btn-save:hover { background: #5558E8; }
.btn-cancel { padding: 7px 18px; border: 1px solid #E2E6EC; border-radius: 6px; background: white; cursor: pointer; font-size: 14px; }
</style>
