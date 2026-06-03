<template>
  <div class="dialog-overlay" @click.self="$emit('close')">
    <div class="dialog">
      <div class="dialog-header">
        <h3>MCP 服务器</h3>
        <button class="btn-refresh" @click="refresh" title="刷新">&#x21bb;</button>
      </div>

      <div v-if="servers.length === 0" class="empty-state">无 MCP 服务器</div>

      <div v-for="s in servers" :key="s.name" class="server-card">
        <div class="server-row">
          <span class="status-dot" :class="statusClass(s.status)" />
          <span class="server-name">{{ s.name }}</span>
          <div class="server-actions">
            <button class="btn-stop" :disabled="!canStop(s.status)" @click="stopServer(s.name)">停止</button>
            <button class="btn-restart" :disabled="!canRestart(s.status)" @click="restartServer(s.name)">重启</button>
          </div>
        </div>
        <details v-if="s.tools && s.tools.length > 0" class="tool-details">
          <summary class="tool-summary">工具 ({{ s.tool_count }})</summary>
          <div v-for="t in s.tools" :key="t.name" class="tool-item">
            <div class="tool-name">{{ t.name }}</div>
            <div class="tool-desc">{{ t.description || '无描述' }}</div>
          </div>
        </details>
      </div>

      <div class="dialog-actions">
        <button class="btn-cancel" @click="$emit('close')">关闭</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue';
import { useAgentStore } from '../stores/agent';
import { agentWs } from '../services/agentWs';

defineEmits<{ close: [] }>();

interface MCPToolInfo {
  name: string;
  description: string;
}

interface MCPServerInfo {
  name: string;
  status: string;
  tool_count: number;
  tools: MCPToolInfo[];
}

interface MCPInfo {
  server_count: number;
  tool_count: number;
  servers: MCPServerInfo[];
}

const agentStore = useAgentStore();

const servers = computed(() => {
  const info = agentStore.mcpInfo as MCPInfo | null;
  return info?.servers ?? [];
});

function statusClass(status: string): string {
  if (status === 'connected') return 'dot-connected';
  if (status === 'failed') return 'dot-failed';
  return 'dot-disconnected';
}

function canStop(status: string): boolean {
  return status === 'connected';
}

function canRestart(status: string): boolean {
  return status === 'disconnected' || status === 'failed';
}

function stopServer(name: string) {
  agentWs.send({ type: 'mcp_stop', server_name: name });
}

function restartServer(name: string) {
  agentWs.send({ type: 'mcp_restart', server_name: name });
}

function refresh() {
  agentWs.send({ type: 'get_status' });
}

function onMcpInfo(d: any) {
  if (d.mcp) agentStore.mcpInfo = d.mcp;
}

onMounted(() => {
  agentWs.on('mcp_info', onMcpInfo);
});

onUnmounted(() => {
  agentWs.off('mcp_info', onMcpInfo);
});
</script>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.dialog {
  background: white;
  border-radius: 12px;
  padding: 20px;
  min-width: 440px;
  max-width: 520px;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.12);
}
.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.dialog-header h3 {
  font-size: 17px;
  color: #1E1B3A;
  margin: 0;
}
.btn-refresh {
  background: none;
  border: 1px solid #E2E6EC;
  border-radius: 6px;
  padding: 4px 10px;
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
}
.btn-refresh:hover {
  background: #F1F5F9;
}
.empty-state {
  color: #94A3B8;
  font-size: 14px;
  text-align: center;
  padding: 24px 0;
}
.server-card {
  border: 1px solid #EEF0F4;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 10px;
}
.server-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot-connected {
  background: #10B981;
}
.dot-failed {
  background: #EF4444;
}
.dot-disconnected {
  background: #94A3B8;
}
.server-name {
  font-size: 14px;
  font-weight: 600;
  color: #1E1B3A;
  flex: 1;
}
.server-actions {
  display: flex;
  gap: 4px;
}
.server-actions button {
  padding: 3px 10px;
  border-radius: 4px;
  border: 1px solid #E2E6EC;
  background: white;
  font-size: 12px;
  cursor: pointer;
}
.server-actions button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.server-actions button:not(:disabled):hover {
  background: #F1F5F9;
}
.btn-stop {
  color: #EF4444;
}
.btn-restart {
  color: #6366F1;
}
.tool-details {
  margin-top: 8px;
}
.tool-summary {
  font-size: 13px;
  color: #64748B;
  cursor: pointer;
  padding: 4px 0;
}
.tool-summary:hover {
  color: #1E1B3A;
}
.tool-item {
  padding: 4px 8px;
  border-left: 2px solid #EEF0F4;
  margin: 4px 0;
}
.tool-name {
  font-size: 13px;
  font-weight: 500;
  color: #1E1B3A;
}
.tool-desc {
  font-size: 12px;
  color: #94A3B8;
  margin-top: 2px;
}
.dialog-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
.btn-cancel {
  padding: 7px 18px;
  border: 1px solid #E2E6EC;
  border-radius: 6px;
  background: white;
  cursor: pointer;
  font-size: 14px;
}
.btn-cancel:hover {
  background: #F1F5F9;
}
</style>
