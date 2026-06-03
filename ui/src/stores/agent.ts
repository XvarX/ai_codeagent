import { ref } from 'vue';
import { defineStore } from 'pinia';

interface AgentInfo {
  id: string;
  name: string;
  status: string;
}

export const useAgentStore = defineStore('agent', () => {
  const busy = ref(false);
  const provider = ref('');
  const model = ref('');
  const agents = ref<AgentInfo[]>([]);
  const mcpInfo = ref<any>(null);
  const skills = ref<string>('');
  const activeAgentId = ref('master');

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

  function setAgentList(list: Array<{ id: string; name: string; status: string; active: boolean }>) {
    agents.value = list;
    const active = list.find(a => a.active);
    if (active) activeAgentId.value = active.id;
  }

  function setBusy(value: boolean) {
    busy.value = value;
  }

  return {
    busy, provider, model, agents, mcpInfo, skills, activeAgentId,
    setFromStatus, setActiveAgent, setAgentList, setBusy,
  };
});
