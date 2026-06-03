<template>
  <div class="dialog-overlay" @click.self="$emit('close')">
    <div class="dialog">
      <h3>MCP Servers</h3>
      <p class="placeholder">MCP server list will be populated from backend status.</p>
      <div class="dialog-actions">
        <button class="btn-cancel" @click="$emit('close')">Close</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineEmits<{ close: [] }>();
</script>

<style scoped>
.dialog-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; z-index: 100; }
.dialog { background: white; border-radius: 12px; padding: 24px; min-width: 360px; }
.dialog h3 { margin-bottom: 16px; }
.placeholder { color: #94A3B8; font-size: 14px; }
.dialog-actions { display: flex; justify-content: flex-end; margin-top: 16px; }
.btn-cancel { padding: 6px 16px; border: 1px solid #E2E6EC; border-radius: 6px; background: white; cursor: pointer; }
</style>
