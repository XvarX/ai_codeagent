import { ref } from 'vue';
import { defineStore } from 'pinia';
import { agentWs } from '../services/agentWs';
import { useAgentStore } from './agent';

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

export interface RoomMessage {
  id: string
  roomId: string
  senderId: string
  senderName: string
  senderColor: string
  content: string
  timestamp: number
  isStreaming: boolean
}

export interface ChatRoomInfo {
  id: string
  name: string
  agentIds: string[]
  createdAt: number
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
  const roomMessages = ref<Map<string, RoomMessage[]>>(new Map())
  const rooms = ref<ChatRoomInfo[]>([])
  const activeRoomId = ref<string | null>(null)
  let _roomMsgId = 0

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

  function _normalizeRoom(r: any): ChatRoomInfo {
    return { id: r.id, name: r.name, agentIds: r.agent_ids || r.agentIds || [], createdAt: r.created_at || r.createdAt || 0 }
  }

  function handleRoomCreated(room: any) {
    rooms.value = [...rooms.value, _normalizeRoom(room)]
  }

  function handleRoomList(roomList: any[]) {
    rooms.value = roomList.map(_normalizeRoom)
  }

  function handleRoomDestroyed(roomId: string) {
    rooms.value = rooms.value.filter(r => r.id !== roomId)
    roomMessages.value.delete(roomId)
    if (activeRoomId.value === roomId) activeRoomId.value = null
  }

  function handleRoomUpdated(room: any) {
    const idx = rooms.value.findIndex(r => r.id === room.id)
    if (idx >= 0) rooms.value[idx] = _normalizeRoom(room)
  }

  function handleRoomBroadcast(data: { room_id: string; agent_id: string; token: string }) {
    const msgs = roomMessages.value.get(data.room_id) || []
    const agent = useAgentStore()
    const agentInfo = agent.agents.find(a => a.id === data.agent_id)
    const senderName = agentInfo?.name || data.agent_id
    const senderColor = agent.getAgentColor(data.agent_id)

    // Find the last streaming message from this specific agent (handle concurrent agent responses)
    let streamingIdx = -1
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].senderId === data.agent_id && msgs[i].isStreaming) {
        streamingIdx = i
        break
      }
    }

    if (streamingIdx >= 0) {
      msgs[streamingIdx].content += data.token
    } else {
      msgs.push({
        id: `rm_${++_roomMsgId}`,
        roomId: data.room_id,
        senderId: data.agent_id,
        senderName,
        senderColor,
        content: data.token,
        timestamp: Date.now(),
        isStreaming: true,
      })
    }
    roomMessages.value.set(data.room_id, msgs)
  }

  function handleRoomDone(data: { room_id: string; agent_id: string }) {
    const msgs = roomMessages.value.get(data.room_id) || []
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].senderId === data.agent_id && msgs[i].isStreaming) {
        msgs[i].isStreaming = false
        break
      }
    }
    roomMessages.value.set(data.room_id, msgs)
  }

  function sendRoomMessage(roomId: string, text: string) {
    agentWs.send({ type: 'room_message', room_id: roomId, text })

    const msgs = roomMessages.value.get(roomId) || []
    msgs.push({
      id: `rm_${++_roomMsgId}`,
      roomId,
      senderId: 'user',
      senderName: '你',
      senderColor: '#89b4fa',
      content: text,
      timestamp: Date.now(),
      isStreaming: false,
    })
    roomMessages.value.set(roomId, msgs)
  }

  return {
    messages, thinking, currentAssistantMsg, diffs, toolLabels,
    maxTokens, usageTokens,
    inputText, insertToInput,
    addUserMessage, startThinking, appendToken, finalizeAssistantMessage,
    addToolResult, addToolCall, addToolResultPreview, addDiff, updateUsage, loadMessages, clear,
    // Room
    roomMessages, rooms, activeRoomId,
    handleRoomCreated, handleRoomList, handleRoomDestroyed, handleRoomUpdated,
    handleRoomBroadcast, handleRoomDone, sendRoomMessage,
  };
});
