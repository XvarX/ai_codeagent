import { ref } from 'vue';
import { defineStore } from 'pinia';

interface ToolCallEntry {
  name: string;
  input: Record<string, any>;
  id: string;
  result?: string;
  isError?: boolean;
  durationMs?: number;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: ToolCallEntry[];
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([]);
  const thinking = ref(false);
  const currentAssistantMsg = ref('');

  function addUserMessage(text: string) {
    messages.value.push({ role: 'user', content: text });
    currentAssistantMsg.value = '';
  }

  function startThinking() {
    thinking.value = true;
  }

  function appendToken(token: string) {
    thinking.value = false;
    currentAssistantMsg.value += token;
  }

  function finalizeAssistantMessage() {
    if (currentAssistantMsg.value) {
      messages.value.push({ role: 'assistant', content: currentAssistantMsg.value });
      currentAssistantMsg.value = '';
    }
    thinking.value = false;
  }

  function addToolResult(name: string, result: string, isError: boolean, durationMs: number) {
    const lastAssistant = messages.value[messages.value.length - 1];
    if (lastAssistant?.role === 'assistant') {
      if (!lastAssistant.toolCalls) lastAssistant.toolCalls = [];
      const existing = lastAssistant.toolCalls.find(tc => tc.name === name);
      if (existing) {
        existing.result = result;
        existing.isError = isError;
        existing.durationMs = durationMs;
      }
    }
  }

  function clear() {
    messages.value = [];
    currentAssistantMsg.value = '';
    thinking.value = false;
  }

  return {
    messages, thinking, currentAssistantMsg,
    addUserMessage, startThinking, appendToken, finalizeAssistantMessage,
    addToolResult, clear,
  };
});
