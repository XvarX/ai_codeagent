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
  toolLabels?: ToolLabel[];
  diffs?: DiffEntry[];
}

export interface ToolLabel {
  name: string;
  input: Record<string, any>;
  isError?: boolean;
  resultPreview?: string;
}

export interface DiffEntry {
  filePath: string;
  oldContent: string;
  newContent: string;
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([]);
  const thinking = ref(false);
  const currentAssistantMsg = ref('');
  const maxTokens = ref(128000);
  const usageTokens = ref(0);
  const diffs = ref<DiffEntry[]>([]);
  const toolLabels = ref<ToolLabel[]>([]);
  const inputText = ref('');

  function addToolCall(name: string, input: Record<string, any>) {
    toolLabels.value.push({ name, input });
  }

  function addToolResultPreview(index: number, resultPreview: string, isError: boolean) {
    if (toolLabels.value[index]) {
      toolLabels.value[index].resultPreview = resultPreview;
      toolLabels.value[index].isError = isError;
    }
  }

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
      messages.value.push({
        role: 'assistant',
        content: currentAssistantMsg.value,
        toolLabels: toolLabels.value.length > 0 ? [...toolLabels.value] : undefined,
        diffs: diffs.value.length > 0 ? [...diffs.value] : undefined,
      } as ChatMessage);
      currentAssistantMsg.value = '';
      toolLabels.value = [];
      diffs.value = [];
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

  function updateUsage(tokens: number) {
    usageTokens.value = tokens;
  }

  function addDiff(filePath: string, oldContent: string, newContent: string) {
    diffs.value.push({ filePath, oldContent, newContent });
  }

  function loadMessages(msgs: Array<{ role: string; content: string; diffs?: DiffEntry[] }>) {
    messages.value = msgs.map(m => ({
      role: m.role as 'user' | 'assistant',
      content: m.content,
      diffs: m.diffs,
    }));
    currentAssistantMsg.value = '';
    thinking.value = false;
  }

  function clear() {
    messages.value = [];
    currentAssistantMsg.value = '';
    thinking.value = false;
    diffs.value = [];
    toolLabels.value = [];
  }

  function insertToInput(text: string) {
    inputText.value += (inputText.value ? ' ' : '') + text;
  }

  return {
    messages, thinking, currentAssistantMsg, diffs, toolLabels,
    maxTokens, usageTokens,
    inputText, insertToInput,
    addUserMessage, startThinking, appendToken, finalizeAssistantMessage,
    addToolResult, addToolCall, addToolResultPreview, addDiff, updateUsage, loadMessages, clear,
  };
});
