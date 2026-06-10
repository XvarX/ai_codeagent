import { ref } from 'vue';
import { defineStore } from 'pinia';

interface AgentInfo {
  id: string;
  name: string;
  status: string;
  est_tokens?: number;
}

export const useAgentStore = defineStore('agent', () => {
  const busy = ref(false);
  const provider = ref('');
  const model = ref('');
  const agents = ref<AgentInfo[]>([]);
  const mcpInfo = ref<any>(null);
  const skills = ref<string>('');
  const activeAgentId = ref('master');
  const compacting = ref(false);

  const AGENT_COLORS = [
    '#89b4fa', '#a6e3a1', '#f9e2af', '#cba6f7',
    '#f38ba8', '#94e2d5', '#fab387', '#74c7ec',
  ]
  const agentColors = ref<Map<string, string>>(new Map())

  function getAgentColor(agentId: string): string {
    if (!agentColors.value.has(agentId)) {
      const idx = agentColors.value.size % AGENT_COLORS.length
      agentColors.value.set(agentId, AGENT_COLORS[idx])
    }
    return agentColors.value.get(agentId)!
  }

  function setFromStatus(data: any) {
    busy.value = data.busy ?? false;
    provider.value = data.config?.provider ?? '';
    model.value = data.config?.model ?? '';
    agents.value = data.agents || [];
    mcpInfo.value = data.mcp || null;
    skills.value = data.skills || '';
    // Set active agent from list
    const active = (data.agents || []).find((a: any) => a.active);
    if (active) activeAgentId.value = active.id;
  }

  function setActiveAgent(id: string) {
    activeAgentId.value = id;
  }

  function setAgentList(list: Array<{ id: string; name: string; status: string; active: boolean; est_tokens?: number }>) {
    agents.value = list;
    const active = list.find(a => a.active);
    if (active) activeAgentId.value = active.id;
  }

  function setBusy(value: boolean) {
    busy.value = value;
  }

  return {
    busy, compacting, provider, model, agents, mcpInfo, skills, activeAgentId,
    agentColors, getAgentColor,
    setFromStatus, setActiveAgent, setAgentList, setBusy,
  };
});
