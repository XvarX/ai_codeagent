<template>
  <div class="dialog-overlay" @click.self="$emit('close')">
    <div class="dialog">
      <h3>MCP Servers</h3>
      <div v-if="agentStore.mcpInfo">
        <div class="mcp-summary">{{ agentStore.mcpInfo.server_count }} servers, {{ agentStore.mcpInfo.tool_count }} tools</div>
        <div v-for="s in agentStore.mcpInfo.servers" :key="s.name" class="mcp-server">
          <div class="server-name">{{ s.name }}</div>
          <div class="server-tools">{{ s.tool_count }} tools: {{ s.tools?.map((t: any) => t.name).join(', ') }}</div>
        </div>
      </div>
      <p v-else class="placeholder">No MCP servers configured.</p>
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
.dialog { background: white; border-radius: 12px; padding: 24px; min-width: 380px; box-shadow: 0 4px 24px rgba(0,0,0,0.12); }
.dialog h3 { margin-bottom: 16px; font-size: 17px; color: #1E1B3A; }
.mcp-summary { font-size: 14px; color: #6366F1; margin-bottom: 12px; }
.mcp-server { padding: 8px; border: 1px solid #EEF0F4; border-radius: 6px; margin-bottom: 8px; }
.server-name { font-size: 14px; font-weight: 600; color: #1E1B3A; }
.server-tools { font-size: 13px; color: #64748B; margin-top: 4px; }
.placeholder { color: #94A3B8; font-size: 14px; }
.dialog-actions { display: flex; justify-content: flex-end; margin-top: 16px; }
.btn-cancel { padding: 7px 18px; border: 1px solid #E2E6EC; border-radius: 6px; background: white; cursor: pointer; font-size: 14px; }
</style>
