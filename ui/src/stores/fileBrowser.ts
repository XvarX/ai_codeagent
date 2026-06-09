import { ref } from 'vue';
import { defineStore } from 'pinia';
import { agentWs } from '../services/agentWs';

export interface TreeNode {
  name: string;
  path: string;
  type: 'file' | 'dir';
  size?: number;
  modified?: string;
  children?: TreeNode[];
  loaded?: boolean;
}

export interface EditorState {
  path: string;
  content: string;
  language: string;
  size: number;
  modified: string;
  dirty: boolean;
}

export const useFileBrowserStore = defineStore('fileBrowser', () => {
  const tree = ref<TreeNode[]>([]);
  const expandedDirs = ref<Set<string>>(new Set());
  const selectedFile = ref<string | null>(null);
  const previewContent = ref<string | null>(null);
  const previewPath = ref<string | null>(null);
  const previewLanguage = ref<string>('text');
  const previewSize = ref<number>(0);
  const previewModified = ref<string>('');
  const openEditors = ref<Map<string, EditorState>>(new Map());
  const panelVisible = ref(false);
  const activeTab = ref<'tree' | string>('tree');
  const loading = ref(false);
  const error = ref<string | null>(null);
  const searchResults = ref<TreeNode[]>([]);
  const searchQuery = ref('');

  const pendingRequests = new Map<string, {
    resolve: (data: any) => void;
    reject: (err: Error) => void;
    timer: ReturnType<typeof setTimeout>;
  }>();
  let requestIdCounter = 0;

  function _nextRequestId(): string {
    return `fb_${++requestIdCounter}_${Date.now()}`;
  }

  function _sendRequest(type: string, params: Record<string, any> = {}): Promise<any> {
    return new Promise((resolve, reject) => {
      const request_id = _nextRequestId();
      const timer = setTimeout(() => {
        pendingRequests.delete(request_id);
        reject(new Error('Request timeout'));
      }, 15000);
      pendingRequests.set(request_id, { resolve, reject, timer });
      agentWs.send({ type, ...params, request_id });
    });
  }

  function handleResponse(data: any) {
    const rid = data.request_id;
    const pending = pendingRequests.get(rid);
    if (pending) {
      clearTimeout(pending.timer);
      pendingRequests.delete(rid);
      if (data.error) {
        pending.reject(new Error(data.error));
      } else {
        pending.resolve(data);
      }
    }
  }

  async function loadDir(path: string | null = null) {
    loading.value = true;
    error.value = null;
    try {
      const data = await _sendRequest('file_list', { path });
      const entries: TreeNode[] = (data.entries || []).map((e: any) => ({
        name: e.name,
        path: e.path,
        type: e.type,
        size: e.size,
        modified: e.modified,
        children: e.type === 'dir' ? [] : undefined,
        loaded: false,
      }));
      if (path === null) {
        tree.value = entries;
      } else {
        _insertChildren(path, entries);
        expandedDirs.value = new Set([...expandedDirs.value, path]);
      }
    } catch (e: any) {
      error.value = e.message;
    } finally {
      loading.value = false;
    }
  }

  async function selectFile(path: string) {
    selectedFile.value = path;
    loading.value = true;
    error.value = null;
    try {
      const data = await _sendRequest('file_read', { path });
      previewContent.value = data.content;
      previewPath.value = path;
      previewLanguage.value = data.language;
      previewSize.value = data.size;
      previewModified.value = data.modified;
      activeTab.value = path;
    } catch (e: any) {
      error.value = e.message;
      previewContent.value = null;
      previewPath.value = null;
    } finally {
      loading.value = false;
    }
  }

  async function openEditor(path: string) {
    if (openEditors.value.has(path)) return;
    loading.value = true;
    error.value = null;
    try {
      const data = await _sendRequest('file_read', { path });
      openEditors.value.set(path, {
        path,
        content: data.content,
        language: data.language,
        size: data.size,
        modified: data.modified,
        dirty: false,
      });
    } catch (e: any) {
      error.value = e.message;
    } finally {
      loading.value = false;
    }
  }

  async function saveFile(path: string, content: string) {
    try {
      const data = await _sendRequest('file_write', { path, content });
      if (data.success) {
        const editor = openEditors.value.get(path);
        if (editor) {
          editor.content = content;
          editor.dirty = false;
        }
      }
      return data.success;
    } catch (e: any) {
      error.value = e.message;
      return false;
    }
  }

  async function searchFiles(query: string) {
    searchQuery.value = query;
    if (!query) {
      searchResults.value = [];
      return;
    }
    try {
      const data = await _sendRequest('file_search', { query });
      searchResults.value = (data.results || []).map((e: any) => ({
        name: e.name,
        path: e.path,
        type: e.type as 'file' | 'dir',
      }));
    } catch (_e: any) {
      searchResults.value = [];
    }
  }

  function closeEditor(path: string) {
    openEditors.value.delete(path);
  }

  function togglePanel() {
    panelVisible.value = !panelVisible.value;
    if (panelVisible.value && tree.value.length === 0) {
      loadDir();
    }
  }

  function closePreview() {
    previewContent.value = null;
    previewPath.value = null;
    activeTab.value = 'tree';
  }

  function _insertChildren(dirPath: string, children: TreeNode[]) {
    function findAndInsert(nodes: TreeNode[]): boolean {
      for (const node of nodes) {
        if (node.type === 'dir' && node.path === dirPath) {
          node.children = children;
          node.loaded = true;
          return true;
        }
        if (node.type === 'dir' && node.children) {
          if (findAndInsert(node.children)) return true;
        }
      }
      return false;
    }
    findAndInsert(tree.value);
  }

  return {
    tree, expandedDirs, selectedFile,
    previewContent, previewPath, previewLanguage, previewSize, previewModified,
    openEditors, panelVisible, activeTab, loading, error,
    searchResults, searchQuery,
    handleResponse,
    loadDir, selectFile, openEditor, saveFile, searchFiles,
    closeEditor, togglePanel, closePreview,
  };
});
