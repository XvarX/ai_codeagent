<template>
  <teleport to="body">
    <div v-for="[path, editor] in fileBrowser.openEditors" :key="path">
      <div
        class="bg-surface-1 border border-border-default flex flex-col"
        :class="maximized ? '' : 'rounded-lg'"
        :style="{ position: 'fixed', ...dialogStyle }"
      >
        <!-- Title bar -->
        <div
          class="flex items-center justify-between px-3 py-2 bg-surface-2 border-b border-border-default cursor-move shrink-0"
          @mousedown.prevent="startDrag($event, path)"
          @dblclick.prevent="toggleMaximize()"
        >
          <div class="flex items-center gap-2 min-w-0">
            <span class="font-mono text-sm text-text-primary truncate">{{ path.split('/').pop() }}</span>
            <span class="text-[10px] text-text-muted truncate max-w-[200px]">{{ path }}</span>
            <span class="text-[10px] text-text-muted">{{ formatSize(editor.size) }}</span>
          </div>
          <div class="flex items-center gap-1.5 shrink-0">
            <button
              class="bg-accent text-white text-xs px-2.5 py-0.5 rounded cursor-pointer hover:bg-accent-hover border-none"
              @click="sendToAgent(path)"
            >→ Agent</button>
            <button
              class="text-xs px-2.5 py-0.5 rounded cursor-pointer border-none"
              :class="editor.dirty ? 'bg-success text-white' : 'bg-surface-3 text-text-secondary hover:bg-surface-4'"
              @click="saveEditor(path)"
            >保存</button>
            <button
              class="text-text-muted hover:text-text-primary text-sm cursor-pointer bg-transparent border-none px-1"
              @click="fileBrowser.closeEditor(path)"
            >✕</button>
          </div>
        </div>

        <!-- Breadcrumb -->
        <div class="px-3 py-1 text-[10px] text-text-muted bg-surface-0 border-b border-border-subtle shrink-0">
          {{ path.split('/').slice(0, -1).join(' › ') || '.' }}
        </div>

        <!-- Editor area -->
        <div class="flex-1 overflow-hidden" :ref="(el: any) => setEditorContainer(el, path)"></div>

        <!-- Dirty indicator -->
        <div v-if="editor.dirty" class="px-3 py-1 text-[10px] text-warning bg-warning-subtle border-t border-border-subtle shrink-0">
          未保存更改
        </div>

        <!-- Bottom resize bar -->
        <div
          v-if="!maximized"
          class="h-2 cursor-ns-resize hover:bg-accent/20 shrink-0"
          @mousedown.prevent="startResize($event, 'vertical')"
        ></div>
      </div>
      <!-- Right edge resize handle (outside overflow) -->
      <div
        v-if="!maximized"
        class="fixed cursor-ew-resize hover:bg-accent/20"
        :style="{ top: dialogY + 'px', left: (dialogX + dialogWidth) + 'px', width: '5px', height: dialogHeight + 'px', zIndex: 51 }"
        @mousedown.prevent="startResize($event, 'horizontal')"
      ></div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue';
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

const maximized = ref(false);
const savedRect = { x: 80, y: 40, w: 800, h: 560 };

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
    dialogX.value = 0;
    dialogY.value = 40; // header height
    dialogWidth.value = window.innerWidth;
    dialogHeight.value = window.innerHeight - 40 - 56; // header + inputbar
    maximized.value = true;
  }
}

const dialogStyle = computed(() => ({
  left: dialogX.value + 'px',
  top: dialogY.value + 'px',
  width: dialogWidth.value + 'px',
  height: dialogHeight.value + 'px',
  zIndex: 50,
  boxShadow: maximized.value ? 'none' : '0 8px 32px rgba(0, 0, 0, 0.12)',
  borderRadius: maximized.value ? '0' : undefined,
  transition: 'left 0.15s, top 0.15s, width 0.15s, height 0.15s',
}));

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

function saveEditor(path: string) {
  const view = editorViews.get(path);
  if (view) {
    fileBrowser.saveFile(path, view.state.doc.toString());
  }
}

function sendToAgent(path: string) {
  chatStore.insertToInput(`@file:${path}`);
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function startDrag(e: MouseEvent, _path: string) {
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
