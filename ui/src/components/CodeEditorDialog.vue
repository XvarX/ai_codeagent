<template>
  <teleport to="body">
    <template v-if="fileBrowser.openEditors.size > 0">
      <div
        class="bg-surface-1 border border-border-default flex flex-col"
        :class="maximized ? '' : 'rounded-lg'"
        :style="{ position: 'fixed', ...dialogStyle }"
      >
        <!-- Tab bar + title bar -->
        <div
          class="flex items-center bg-surface-2 border-b border-border-default cursor-move shrink-0"
          @mousedown.prevent="startDrag($event)"
          @dblclick.prevent="toggleMaximize()"
        >
          <!-- File tabs -->
          <div class="flex items-center overflow-x-auto flex-1 min-w-0">
            <button
              v-for="[path, editor] in fileBrowser.openEditors"
              :key="path"
              class="flex items-center gap-1 px-2.5 py-1.5 text-xs whitespace-nowrap cursor-pointer border-none transition-colors"
              :class="activeTab === path
                ? 'bg-surface-1 text-text-primary border-b-2 border-accent'
                : 'bg-transparent text-text-muted hover:text-text-secondary border-b-2 border-transparent'"
              @mousedown.prevent.stop
              @click.stop="activeTab = path"
            >
              <span class="font-mono truncate max-w-[120px]">{{ path.split('/').pop() }}</span>
              <span v-if="editor.dirty" class="w-1.5 h-1.5 rounded-full bg-warning shrink-0"></span>
              <span
                class="text-text-muted hover:text-text-primary ml-0.5 text-[10px]"
                @click.stop="closeTab(path)"
              >✕</span>
            </button>
          </div>
          <!-- Action buttons -->
          <div class="flex items-center gap-1.5 shrink-0 px-2">
            <button
              v-if="activeTab"
              class="bg-accent text-white text-xs px-2 py-0.5 rounded cursor-pointer hover:bg-accent-hover border-none"
              @click.stop="sendToAgent(activeTab)"
            >→ Agent</button>
            <button
              v-if="activeTab"
              class="text-xs px-2 py-0.5 rounded cursor-pointer border-none"
              :class="activeEditor?.dirty ? 'bg-success text-white' : 'bg-surface-3 text-text-secondary hover:bg-surface-4'"
              @click.stop="saveEditor(activeTab)"
            >保存</button>
            <button
              class="text-text-muted hover:text-text-primary text-sm cursor-pointer bg-transparent border-none px-1"
              @click.stop="closeAll"
            >✕</button>
          </div>
        </div>

        <!-- Breadcrumb for active file -->
        <div v-if="activeTab" class="px-3 py-1 text-[10px] text-text-muted bg-surface-0 border-b border-border-subtle shrink-0">
          {{ activeTab.split('/').slice(0, -1).join(' › ') || '.' }}
          <span class="ml-2">{{ formatSize(activeEditor?.size || 0) }}</span>
        </div>

        <!-- Editor containers (one per open file, show/hide) -->
        <div class="flex-1 relative overflow-hidden">
          <div
            v-for="[path] in fileBrowser.openEditors"
            :key="path"
            class="absolute inset-0"
            :style="{ display: path === activeTab ? 'block' : 'none' }"
            :ref="(el: any) => setEditorContainer(el, path)"
          ></div>
        </div>

        <!-- Dirty indicator -->
        <div v-if="activeEditor?.dirty" class="px-3 py-1 text-[10px] text-warning bg-warning-subtle border-t border-border-subtle shrink-0">
          未保存更改
        </div>

        <!-- Bottom resize bar -->
        <div
          v-if="!maximized"
          class="h-2 cursor-ns-resize hover:bg-accent/20 shrink-0"
          @mousedown.prevent="startResize($event, 'vertical')"
        ></div>
      </div>
      <!-- Right edge resize handle -->
      <div
        v-if="!maximized"
        class="fixed cursor-ew-resize hover:bg-accent/20"
        :style="{ top: dialogY + 'px', left: (dialogX + dialogWidth) + 'px', width: '5px', height: dialogHeight + 'px', zIndex: 51 }"
        @mousedown.prevent="startResize($event, 'horizontal')"
      ></div>
    </template>
  </teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue';
import { useFileBrowserStore } from '../stores/fileBrowser';
import { useChatStore } from '../stores/chat';
import { EditorView, keymap, lineNumbers, highlightActiveLine } from '@codemirror/view';
import { EditorState as CMState } from '@codemirror/state';
import { defaultKeymap, indentWithTab, history, historyKeymap } from '@codemirror/commands';
import { syntaxHighlighting, defaultHighlightStyle, bracketMatching } from '@codemirror/language';
import { oneDark } from '@codemirror/theme-one-dark';
import { searchKeymap } from '@codemirror/search';
import { autocompletion, completionKeymap } from '@codemirror/autocomplete';
import { python } from '@codemirror/lang-python';
import { javascript } from '@codemirror/lang-javascript';
import { html } from '@codemirror/lang-html';
import { css } from '@codemirror/lang-css';
import { json } from '@codemirror/lang-json';
import { markdown } from '@codemirror/lang-markdown';
import { rust } from '@codemirror/lang-rust';
import { yaml } from '@codemirror/lang-yaml';

const fileBrowser = useFileBrowserStore();
const chatStore = useChatStore();

const dialogX = ref(80);
const dialogY = ref(40);
const dialogWidth = ref(800);
const dialogHeight = ref(560);
const minWidth = 400;
const minHeight = 300;

const activeTab = ref<string | null>(null);
const maximized = ref(false);
const savedRect = { x: 80, y: 40, w: 800, h: 560 };

const activeEditor = computed(() => {
  if (!activeTab.value) return null;
  return fileBrowser.openEditors.get(activeTab.value) || null;
});

// Sync activeTab when editors change
watch(
  () => [...fileBrowser.openEditors.keys()],
  (keys, oldKeys) => {
    if (keys.length === 0) {
      activeTab.value = null;
    } else {
      const added = keys.filter((k: string) => !oldKeys.includes(k));
      if (added.length > 0) {
        activeTab.value = added[added.length - 1];
      } else if (!activeTab.value || !fileBrowser.openEditors.has(activeTab.value)) {
        activeTab.value = keys[keys.length - 1];
      }
    }
    nextTick(() => mountPendingEditors());
  }
);

// Direct callback for re-focusing already-open files (bypasses reactivity)
onMounted(() => {
  fileBrowser.onEditorFocus((path) => {
    activeTab.value = path;
  });
});

const dialogStyle = computed(() => ({
  left: dialogX.value + 'px',
  top: dialogY.value + 'px',
  width: dialogWidth.value + 'px',
  height: dialogHeight.value + 'px',
  zIndex: 50,
  boxShadow: maximized.value ? 'none' : '0 8px 32px rgba(0, 0, 0, 0.12)',
  borderRadius: maximized.value ? '0' : undefined,
  transition: maximized.value ? 'left 0.15s, top 0.15s, width 0.15s, height 0.15s' : undefined,
}));

function toggleMaximize() {
  if (maximized.value) {
    dialogX.value = savedRect.x;
    dialogY.value = savedRect.y;
    dialogWidth.value = savedRect.w;
    dialogHeight.value = savedRect.h;
    maximized.value = false;
  } else {
    savedRect.x = dialogX.value;
    savedRect.y = dialogY.value;
    savedRect.w = dialogWidth.value;
    savedRect.h = dialogHeight.value;
    const chatArea = document.getElementById('chat-area');
    if (chatArea) {
      const rect = chatArea.getBoundingClientRect();
      dialogX.value = rect.left;
      dialogY.value = rect.top;
      dialogWidth.value = rect.width;
      dialogHeight.value = rect.height;
    } else {
      dialogX.value = 0;
      dialogY.value = 40;
      dialogWidth.value = window.innerWidth;
      dialogHeight.value = window.innerHeight - 96;
    }
    maximized.value = true;
  }
}

const editorViews = new Map<string, EditorView>();

function getLanguageExtension(lang: string) {
  switch (lang) {
    case 'python': return python();
    case 'javascript':
    case 'typescript': return javascript({ typescript: lang === 'typescript' });
    case 'html': return html();
    case 'css': return css();
    case 'json': return json();
    case 'markdown': return markdown();
    case 'rust': return rust();
    case 'yaml': return yaml();
    default: return [];
  }
}

function setEditorContainer(el: any, path: string) {
  if (!el) return;
  const editor = fileBrowser.openEditors.get(path);
  if (editor && !editorViews.has(path)) {
    createEditor(path, editor, el as HTMLElement);
  }
}

function mountPendingEditors() {
  for (const [path, editor] of fileBrowser.openEditors) {
    if (!editorViews.has(path)) {
      const container = document.querySelector(`[data-editor-path="${CSS.escape(path)}"]`);
      if (container) createEditor(path, editor, container as HTMLElement);
    }
  }
}

function createEditor(path: string, editor: { content: string; language: string }, container: HTMLElement) {
  const extensions = [
    lineNumbers(),
    highlightActiveLine(),
    history(),
    bracketMatching(),
    syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
    oneDark,
    keymap.of([
      ...defaultKeymap,
      ...historyKeymap,
      ...searchKeymap,
      ...completionKeymap,
      indentWithTab,
      {
        key: 'Mod-s',
        run: () => { saveEditor(path); return true; },
      },
    ]),
    autocompletion(),
    getLanguageExtension(editor.language),
    EditorView.updateListener.of((update) => {
      if (update.docChanged) {
        const ed = fileBrowser.openEditors.get(path);
        if (ed) ed.dirty = true;
      }
    }),
    EditorView.theme({
      '&': { height: '100%' },
      '.cm-scroller': { overflow: 'auto' },
    }),
  ];

  const view = new EditorView({
    state: CMState.create({ doc: editor.content, extensions }),
    parent: container,
  });
  editorViews.set(path, view);
}

function saveEditor(path: string | null) {
  if (!path) return;
  const view = editorViews.get(path);
  if (view) {
    fileBrowser.saveFile(path, view.state.doc.toString());
  }
}

function sendToAgent(path: string | null) {
  if (!path) return;
  chatStore.insertToInput(`@file:${path}`);
}

function closeTab(path: string) {
  fileBrowser.closeEditor(path);
  const view = editorViews.get(path);
  if (view) {
    view.destroy();
    editorViews.delete(path);
  }
}

function closeAll() {
  for (const [path, view] of editorViews) {
    view.destroy();
    fileBrowser.closeEditor(path);
  }
  editorViews.clear();
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function startDrag(e: MouseEvent) {
  if (maximized.value) return;
  const startX = e.clientX;
  const startY = e.clientY;
  const origX = dialogX.value;
  const origY = dialogY.value;
  function onMove(ev: MouseEvent) {
    dialogX.value = origX + (ev.clientX - startX);
    dialogY.value = Math.max(0, origY + (ev.clientY - startY));
  }
  function onUp() {
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
  }
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
}

function startResize(e: MouseEvent, direction: 'vertical' | 'horizontal') {
  const startX = e.clientX;
  const startY = e.clientY;
  const origW = dialogWidth.value;
  const origH = dialogHeight.value;
  function onMove(ev: MouseEvent) {
    if (direction === 'horizontal') {
      dialogWidth.value = Math.max(minWidth, origW + (ev.clientX - startX));
    } else {
      dialogHeight.value = Math.max(minHeight, origH + (ev.clientY - startY));
    }
  }
  function onUp() {
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
  }
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
}

// Clean up editor views when closed externally (e.g. from fileBrowser store)
watch(
  () => [...fileBrowser.openEditors.keys()],
  (newKeys) => {
    for (const [path, view] of editorViews) {
      if (!newKeys.includes(path)) {
        view.destroy();
        editorViews.delete(path);
      }
    }
  }
);

onUnmounted(() => {
  for (const view of editorViews.values()) view.destroy();
  editorViews.clear();
});
</script>
