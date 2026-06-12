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

export interface PvtInfo {
  direction: 'in' | 'out'
  targetName: string
  targetId?: string
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: ToolCallEntry[];
  toolLabels?: ToolLabel[];
  diffs?: DiffEntry[];
  roomInfo?: RoomInfo;
  pvtInfo?: PvtInfo;
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

export interface RoomInfo {
  roomId: string
  roomName: string
  senderName?: string
  senderId?: string
  direction: 'in' | 'out'
  replyTo?: string
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
  // Deduplicate room_relay events (multiple agents may each emit one for the same broadcast)
  const _roomRelaySeen = new Set<string>()
  // Buffer for non-active-agent relays — flushed when active agent finishes
  let _relayBuffer: ChatMessage[] = []
  // Track active agent busy state (room + non-room) for relay buffering
  let _busyCounter = 0




  function addToolCall(name: string, input: Record<string, any>) {
    toolLabels.value.push({ name, input });
    // Push SendMessage bubble immediately — don't wait for finalizeAssistantMessage
    if (name === 'SendMessage') {
      messages.value.push({
        role: 'assistant',
        content: input?.message || '',
        pvtInfo: {
          direction: 'out',
          targetName: input?.to || '',
        },
      } as ChatMessage);
    }
  }

  function addToolResultPreview(index: number, resultPreview: string, isError: boolean) {
    if (toolLabels.value[index]) {
      toolLabels.value[index].resultPreview = resultPreview;
      toolLabels.value[index].isError = isError;
    }
  }

  function addUserMessage(text: string) {
    _flushRelayBuffer();
    messages.value.push({ role: 'user', content: text });
    currentAssistantMsg.value = '';
  }

  function startThinking() {
    thinking.value = true;
    _busyCounter++;
  }

  function appendToken(token: string) {
    thinking.value = false;
    currentAssistantMsg.value += token;
  }

  function _flushRelayBuffer() {
    if (_relayBuffer.length === 0) return
    for (const msg of _relayBuffer) {
      messages.value.push(msg)
    }
    _relayBuffer = []
  }

  function finalizeAssistantMessage() {
    // Flush buffered relays BEFORE the agent's own response — other agents'
    // broadcasts happened earlier and should appear first.
    _flushRelayBuffer();
    if (currentAssistantMsg.value) {
      messages.value.push({
        role: 'assistant',
        content: currentAssistantMsg.value,
        toolLabels: toolLabels.value.length > 0 ? [...toolLabels.value] : undefined,
        diffs: diffs.value.length > 0 ? [...diffs.value] : undefined,
      } as ChatMessage);
      currentAssistantMsg.value = '';
    }
    toolLabels.value = [];
    diffs.value = [];
    thinking.value = false;
    if (_busyCounter > 0) _busyCounter--;
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

  function loadMessages(msgs: Array<{ role: string; content: string; diffs?: DiffEntry[]; roomInfo?: RoomInfo; pvtInfo?: PvtInfo }>) {
    messages.value = msgs.map(m => ({
      role: m.role as 'user' | 'assistant',
      content: m.content,
      diffs: m.diffs,
      roomInfo: m.roomInfo,
      pvtInfo: m.pvtInfo,
    }));
    currentAssistantMsg.value = '';
    thinking.value = false;
    _relayBuffer = [];
    _roomRelaySeen.clear();
    _busyCounter = 0;
  }

  function clear() {
    messages.value = [];
    currentAssistantMsg.value = '';
    thinking.value = false;
    diffs.value = [];
    toolLabels.value = [];
    rooms.value = [];
    roomMessages.value = new Map();
    activeRoomId.value = null;
    _roomRelaySeen.clear();
    _relayBuffer = [];
    _busyCounter = 0;
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
    const newMap = new Map(roomMessages.value)
    newMap.delete(roomId)
    roomMessages.value = newMap
    if (activeRoomId.value === roomId) activeRoomId.value = null
  }

  function handleRoomUpdated(room: any) {
    const idx = rooms.value.findIndex(r => r.id === room.id)
    if (idx >= 0) rooms.value[idx] = _normalizeRoom(room)
  }

  function _setRoomMessages(roomId: string, msgs: RoomMessage[]) {
    roomMessages.value = new Map(roomMessages.value).set(roomId, msgs)
  }

  function handleRoomBroadcast(data: { room_id: string; agent_id: string; token: string }) {
    const msgs = roomMessages.value.get(data.room_id) || []
    const agent = useAgentStore()
    const agentInfo = agent.agents.find(a => a.id === data.agent_id)
    const senderName = agentInfo?.name || data.agent_id
    const senderColor = agent.getAgentColor(data.agent_id)

    // Track active agent's room processing for relay buffering
    if (data.agent_id === agent.activeAgentId) {
      _busyCounter++
    }

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
    _setRoomMessages(data.room_id, msgs)
  }

  function handleRoomDone(data: { room_id: string; agent_id: string; final_text?: string }) {
    // Clear any leftover streaming state from main chat
    currentAssistantMsg.value = ''
    thinking.value = false
    toolLabels.value = []
    diffs.value = []

    const msgs = roomMessages.value.get(data.room_id) || []
    let finalizedContent = (data.final_text && data.final_text !== '(no response)') ? data.final_text : ''
    // Also finalize any streaming message if present
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].senderId === data.agent_id && msgs[i].isStreaming) {
        msgs[i].isStreaming = false
        if (!finalizedContent) finalizedContent = msgs[i].content
        break
      }
    }
    _setRoomMessages(data.room_id, msgs)

    // Flush buffered relays FIRST — other agents' broadcasts happened earlier
    // and should appear before the active agent's own response.
    const agent = useAgentStore()
    if (data.agent_id === agent.activeAgentId) {
      if (_busyCounter > 0) _busyCounter--
      _flushRelayBuffer()
    }
    // Only show in main chat if this is the ACTIVE agent's own response.
    if (finalizedContent && data.agent_id === agent.activeAgentId) {
      messages.value.push({ role: 'assistant', content: finalizedContent })
    }
  }

  function handleRoomRelay(data: { room_id: string; room_name: string; from_name: string; from_id: string; text: string; reply_to: string }) {
    const agent = useAgentStore()

    // Deduplicate: same broadcast may arrive twice (once from BroadcastRoom,
    // once from _consumer_loop).  Only process the first.
    const dedupeKey = `${data.room_id}:${data.from_id}:${data.text}`
    if (_roomRelaySeen.has(dedupeKey)) return
    _roomRelaySeen.add(dedupeKey)
    if (_roomRelaySeen.size > 200) {
      const iter = _roomRelaySeen.values()
      for (let i = 0; i < 100; i++) _roomRelaySeen.delete(iter.next().value)
    }

    const isActiveAgent = data.from_id === agent.activeAgentId
    const relayMsg: ChatMessage = {
      role: (isActiveAgent ? 'assistant' : 'user') as 'user' | 'assistant',
      content: data.text,
      roomInfo: {
        roomId: data.room_id,
        roomName: data.room_name,
        senderName: data.from_name,
        senderId: data.from_id,
        direction: 'in' as const,
        replyTo: data.reply_to || undefined,
      },
    }

    // Active agent's own broadcast → show immediately.
    // Other agents' broadcasts when active agent is busy → buffer.
    // Other agents' broadcasts when active agent is idle → show immediately.
    if (isActiveAgent) {
      messages.value.push(relayMsg)
    } else if (_busyCounter > 0) {
      _relayBuffer.push(relayMsg)
    } else {
      messages.value.push(relayMsg)
    }
  }

  function handlePrivateMessage(data: { from_name: string; from_id: string; text: string }) {
    messages.value.push({
      role: 'user',
      content: data.text,
      pvtInfo: {
        direction: 'in',
        targetName: data.from_name,
        targetId: data.from_id,
      },
    } as ChatMessage);
  }

  function handleRoomChat(data: { room_id: string; room_name: string; from_name: string; from_id: string; text: string; reply_to: string }) {
    if (!data.room_id) return
    const agent = useAgentStore()
    const msgs = roomMessages.value.get(data.room_id) || []
    msgs.push({
      id: `rm_${++_roomMsgId}`,
      roomId: data.room_id,
      senderId: data.from_id,
      senderName: data.from_name,
      senderColor: agent.getAgentColor(data.from_id),
      content: data.text,
      timestamp: Date.now(),
      isStreaming: false,
    })
    _setRoomMessages(data.room_id, msgs)
  }

  function sendRoomMessage(roomId: string, text: string) {
    // Flush any stale buffered relays first — new interaction starts now
    _flushRelayBuffer()
    agentWs.send({ type: 'room_message', room_id: roomId, text })

    const room = rooms.value.find(r => r.id === roomId)
    // Add to chatroom message stream
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
    _setRoomMessages(roomId, msgs)

    // Show in main chat (right side — user message)
    currentAssistantMsg.value = ''
    messages.value.push({
      role: 'user',
      content: text,
      roomInfo: {
        roomId,
        roomName: room?.name || '',
        direction: 'out',
      },
    })
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
    handleRoomBroadcast, handleRoomDone, handleRoomRelay, handleRoomChat, handlePrivateMessage, sendRoomMessage,
  };
});
