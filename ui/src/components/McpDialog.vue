<template>
  <div class="fixed inset-0 bg-black/50 flex items-center justify-center z-[100]" @click.self="$emit('close')">
    <div class="bg-surface-1 rounded-xl p-5 min-w-[440px] max-w-[520px] max-h-[80vh] overflow-y-auto shadow-dialog">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-[17px] font-semibold text-text-primary m-0">MCP 服务器</h3>
        <button class="bg-transparent border border-border-default rounded-md px-[10px] py-1 cursor-pointer text-base leading-none hover:bg-surface-2 text-text-secondary" @click="refresh" title="刷新">&#x21bb;</button>
      </div>

      <div v-if="servers.length === 0" class="text-text-muted text-sm text-center py-6">无 MCP 服务器</div>

      <div v-for="s in servers" :key="s.name" class="border border-border-subtle rounded-lg p-[10px_12px] mb-[10px]">
        <div class="flex items-center gap-2">
          <span class="w-[10px] h-[10px] rounded-full flex-shrink-0" :class="statusClass(s.status)"></span>
          <span class="text-sm font-semibold text-text-primary flex-1">{{ s.name }}</span>
          <div class="flex gap-1">
            <button class="px-[10px] py-[3px] rounded border border-border-default bg-transparent text-xs cursor-pointer text-danger disabled:opacity-40 disabled:cursor-not-allowed hover:bg-surface-2" :disabled="!canStop(s.status)" @click="stopServer(s.name)">停止</button>
            <button class="px-[10px] py-[3px] rounded border border-border-default bg-transparent text-xs cursor-pointer text-accent disabled:opacity-40 disabled:cursor-not-allowed hover:bg-surface-2" :disabled="!canRestart(s.status)" @click="restartServer(s.name)">重启</button>
          </div>
        </div>
        <details v-if="s.tools && s.tools.length > 0" class="mt-2">
          <summary class="text-[13px] text-text-secondary cursor-pointer py-1 hover:text-text-primary">工具 ({{ s.tool_count }})</summary>
          <div v-for="t in s.tools" :key="t.name" class="py-1 px-2 border-l-2 border-border-subtle my-1">
            <div class="text-[13px] font-medium text-text-primary">{{ t.name }}</div>
            <div class="text-xs text-text-muted mt-0.5">{{ t.description || '无描述' }}</div>
          </div>
        </details>
      </div>

      <div class="flex justify-end mt-4">
        <button class="px-[18px] py-[7px] border border-border-default rounded-md bg-transparent cursor-pointer text-sm text-text-primary hover:bg-surface-2" @click="$emit('close')">关闭</button>
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
  if (status === 'connected') return 'bg-success';
  if (status === 'failed') return 'bg-danger';
  return 'bg-text-muted';
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
