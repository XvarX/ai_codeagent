<template>
  <div class="dialog-overlay" @click.self="$emit('close')">
    <div class="dialog">
      <h3>配置</h3>
      <label class="field">Provider <input v-model="provider" class="input" /></label>
      <label class="field">Model <input v-model="model" class="input" /></label>
      <label class="field">API Key <input v-model="apiKey" type="password" class="input" /></label>
      <label class="field">Base URL <input v-model="baseUrl" class="input" /></label>
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

defineEmits<{ close: [] }>();

const agentStore = useAgentStore();
const provider = ref(agentStore.provider);
const model = ref(agentStore.model);
const apiKey = ref('');
const baseUrl = ref('');

function save() {
  agentWs.send({ type: 'reconfigure', config: { provider: provider.value, model: model.value, api_key: apiKey.value, base_url: baseUrl.value } });
}
</script>

<style scoped>
.dialog-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; z-index: 100; }
.dialog { background: white; border-radius: 12px; padding: 24px; min-width: 360px; }
.dialog h3 { margin-bottom: 16px; font-size: 17px; }
.field { display: block; margin-bottom: 12px; font-size: 14px; color: #64748B; }
.input { display: block; width: 100%; padding: 6px 10px; border: 1px solid #E2E6EC; border-radius: 6px; font-size: 15px; margin-top: 4px; }
.dialog-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
.btn-save { padding: 6px 16px; border: none; border-radius: 6px; background: #6366F1; color: white; cursor: pointer; }
.btn-cancel { padding: 6px 16px; border: 1px solid #E2E6EC; border-radius: 6px; background: white; cursor: pointer; }
</style>
