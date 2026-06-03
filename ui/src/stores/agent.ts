import { ref } from 'vue';
import { defineStore } from 'pinia';

export const useAgentStore = defineStore('agent', () => {
  const busy = ref(false);
  const provider = ref('');
  const model = ref('');

  function setFromStatus(data: any) {
    busy.value = data.busy ?? false;
    provider.value = data.config?.provider ?? '';
    model.value = data.config?.model ?? '';
  }

  function setBusy(value: boolean) {
    busy.value = value;
  }

  return { busy, provider, model, setFromStatus, setBusy };
});
