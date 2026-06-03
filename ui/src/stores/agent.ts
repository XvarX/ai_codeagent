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

  function setFromStatus(data: any) {
    busy.value = data.busy ?? false;
    provider.value = data.config?.provider ?? '';
    model.value = data.config?.model ?? '';
    agents.value = data.agents || [];
  }

  function setBusy(value: boolean) {
    busy.value = value;
  }

  return { busy, provider, model, agents, setFromStatus, setBusy };
});
