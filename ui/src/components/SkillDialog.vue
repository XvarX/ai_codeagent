<template>
  <div class="dialog-overlay" @click.self="$emit('close')">
    <div class="dialog">
      <h3>Skills</h3>
      <div v-if="agentStore.skills" class="skills-text">
        <pre>{{ agentStore.skills }}</pre>
      </div>
      <p v-else class="placeholder">No skills loaded.</p>
      <div class="dialog-actions">
        <button class="btn-cancel" @click="$emit('close')">Close</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAgentStore } from '../stores/agent';
defineEmits<{ close: [] }>();
const agentStore = useAgentStore();
</script>

<style scoped>
.dialog-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; z-index: 100; }
.dialog { background: white; border-radius: 12px; padding: 24px; min-width: 380px; max-width: 500px; box-shadow: 0 4px 24px rgba(0,0,0,0.12); }
.dialog h3 { margin-bottom: 16px; font-size: 17px; color: #1E1B3A; }
.skills-text pre { font-size: 13px; color: #475569; white-space: pre-wrap; font-family: Consolas, monospace; background: #F8F9FB; padding: 12px; border-radius: 6px; border: 1px solid #EEF0F4; max-height: 400px; overflow-y: auto; }
.placeholder { color: #94A3B8; font-size: 14px; }
.dialog-actions { display: flex; justify-content: flex-end; margin-top: 16px; }
.btn-cancel { padding: 7px 18px; border: 1px solid #E2E6EC; border-radius: 6px; background: white; cursor: pointer; font-size: 14px; }
</style>
