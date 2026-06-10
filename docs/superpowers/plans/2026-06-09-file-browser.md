# File Browser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a file browser to the AI Code Agent desktop app, allowing users to browse project files, preview code, edit files, and send files to the agent via WebSocket.

**Architecture:** Backend exposes 4 WebSocket message types (file_list, file_read, file_write, file_search) handled by a new `FileBrowserHandler` class. Frontend uses a new Pinia store (`fileBrowser.ts`), a `FileTreePanel.vue` component with tab-based preview, and a `CodeEditorDialog.vue` component built on CodeMirror 6. All file operations go through WebSocket → Python backend → filesystem, since the backend may run on a different machine.

**Tech Stack:** Python (os/pathlib), Vue 3 Composition API, Pinia, CodeMirror 6, Tailwind CSS 4, WebSocket JSON

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `agentcore/file_browser.py` | Backend file browser handler: list_dir, read_file, write_file, search. Path safety, binary detection, language inference. |
| `tests/test_file_browser.py` | Unit tests for FileBrowserHandler |
| `ui/src/stores/fileBrowser.ts` | Pinia store: tree state, preview, editor state, WebSocket actions |
| `ui/src/components/FileTreePanel.vue` | Left panel: file tree with lazy-load dirs, tab bar, compact preview, search box |
| `ui/src/components/CodeEditorDialog.vue` | Floating dialog: CodeMirror 6 editor, drag-move, save, send-to-agent |

### Modified Files

| File | Change |
|------|--------|
| `agentcore/ws_server.py` | Add 4 message type handlers in the if/elif chain (after `list_all_sessions`, before `shutdown`) |
| `ui/src/App.vue` | Import and integrate FileTreePanel, CodeEditorDialog, icon bar button |
| `ui/src/stores/chat.ts` | Add `inputText` ref and `insertToInput()` function |
| `ui/src/components/InputBar.vue` | Bind textarea to `chatStore.inputText` instead of local ref |
| `ui/package.json` | Add CodeMirror 6 dependencies |

---

## Task 1: Backend — FileBrowserHandler

**Files:**
- Create: `agentcore/file_browser.py`
- Create: `tests/test_file_browser.py`

- [ ] **Step 1: Write failing tests for FileBrowserHandler**

```python
# tests/test_file_browser.py
import tempfile
import os
from pathlib import Path
import pytest
from agentcore.file_browser import FileBrowserHandler, BINARY_EXTENSIONS


def _setup_project(tmp: str) -> str:
    """Create a sample project directory structure."""
    os.makedirs(os.path.join(tmp, "src"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "docs"), exist_ok=True)
    Path(tmp, "main.py").write_text("print('hello')\n", encoding="utf-8")
    Path(tmp, "src", "utils.py").write_text("def add(a, b): return a + b\n", encoding="utf-8")
    Path(tmp, "README.md").write_text("# Test Project\n", encoding="utf-8")
    Path(tmp, "data.bin").write_bytes(b"\x00\x01\x02\xff\xfe")
    return tmp


class TestListDir:
    def test_list_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            _setup_project(tmp)
            h = FileBrowserHandler(tmp)
            entries = h.list_dir(None)
            names = {e["name"] for e in entries}
            assert "main.py" in names
            assert "src" in names
            assert "docs" in names
            assert "README.md" in names

    def test_list_subdir(self):
        with tempfile.TemporaryDirectory() as tmp:
            _setup_project(tmp)
            h = FileBrowserHandler(tmp)
            entries = h.list_dir("src")
            names = {e["name"] for e in entries}
            assert "utils.py" in names

    def test_list_dir_entry_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            _setup_project(tmp)
            h = FileBrowserHandler(tmp)
            entries = h.list_dir(None)
            by_name = {e["name"]: e for e in entries}
            assert by_name["main.py"]["type"] == "file"
            assert by_name["src"]["type"] == "dir"
            assert by_name["main.py"]["size"] > 0
            assert "modified" in by_name["main.py"]

    def test_list_nonexistent_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = FileBrowserHandler(tmp)
            with pytest.raises(FileNotFoundError):
                h.list_dir("nope")


class TestReadFile:
    def test_read_text_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            _setup_project(tmp)
            h = FileBrowserHandler(tmp)
            result = h.read_file("main.py")
            assert result["content"] == "print('hello')\n"
            assert result["language"] == "python"
            assert result["size"] > 0

    def test_read_binary_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            _setup_project(tmp)
            h = FileBrowserHandler(tmp)
            with pytest.raises(ValueError, match="binary"):
                h.read_file("data.bin")

    def test_read_nonexistent_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = FileBrowserHandler(tmp)
            with pytest.raises(FileNotFoundError):
                h.read_file("nope.py")


class TestWriteFile:
    def test_write_new_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            _setup_project(tmp)
            h = FileBrowserHandler(tmp)
            h.write_file("main.py", "print('updated')\n")
            assert Path(tmp, "main.py").read_text() == "print('updated')\n"

    def test_write_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = FileBrowserHandler(tmp)
            h.write_file("deep/nested/file.txt", "hello")
            assert Path(tmp, "deep", "nested", "file.txt").read_text() == "hello"


class TestSearch:
    def test_search_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            _setup_project(tmp)
            h = FileBrowserHandler(tmp)
            results = h.search("main")
            paths = [r["path"] for r in results]
            assert any("main.py" in p for p in paths)

    def test_search_no_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            _setup_project(tmp)
            h = FileBrowserHandler(tmp)
            results = h.search("zzzznonexistent")
            assert len(results) == 0


class TestPathSafety:
    def test_reject_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = FileBrowserHandler(tmp)
            with pytest.raises(ValueError, match="outside"):
                h.read_file("../../etc/passwd")

    def test_reject_absolute_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = FileBrowserHandler(tmp)
            with pytest.raises(ValueError, match="outside"):
                h.read_file("/etc/passwd")

    def test_reject_symlink_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            _setup_project(tmp)
            link = Path(tmp, "evil_link")
            link.symlink_to(Path(tmp).parent)
            h = FileBrowserHandler(tmp)
            with pytest.raises(ValueError, match="outside"):
                h.list_dir("evil_link")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:\space\labspace\ai_codeagent && python -m pytest tests/test_file_browser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agentcore.file_browser'`

- [ ] **Step 3: Implement FileBrowserHandler**

```python
# agentcore/file_browser.py
"""File browser handler — list, read, write, search project files."""

import os
from pathlib import Path
from datetime import datetime, timezone

BINARY_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svg",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".dat",
    ".mp3", ".mp4", ".wav", ".avi", ".mkv", ".mov",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".pyc", ".pyo", ".class", ".o", ".obj",
    ".sqlite", ".db",
})

EXT_TO_LANGUAGE = {
    ".py": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".vue": "vue", ".svelte": "svelte",
    ".html": "html", ".htm": "html",
    ".css": "css", ".scss": "css", ".less": "css",
    ".json": "json",
    ".md": "markdown", ".mdx": "markdown",
    ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell",
    ".bat": "bat", ".cmd": "bat",
    ".sql": "sql",
    ".xml": "xml",
    ".ini": "ini", ".cfg": "ini",
    ".dockerfile": "dockerfile",
    ".rs": "rust",
    ".swift": "swift",
    ".kt": "kotlin",
    ".lua": "lua",
    ".r": "r", ".R": "r",
}


def _infer_language(filename: str) -> str:
    name = filename.lower()
    if name == "dockerfile":
        return "dockerfile"
    if name == "makefile":
        return "makefile"
    ext = Path(filename).suffix.lower()
    return EXT_TO_LANGUAGE.get(ext, "text")


def _is_binary(filename: str) -> bool:
    ext = Path(filename).suffix.lower()
    return ext in BINARY_EXTENSIONS


class FileBrowserHandler:
    """Handles file browsing operations relative to a project root (cwd)."""

    def __init__(self, cwd: str):
        self.cwd = Path(cwd).resolve()

    def _resolve(self, rel_path: str | None) -> Path:
        """Resolve a relative path against cwd, with path-safety checks."""
        if rel_path is None:
            return self.cwd
        resolved = (self.cwd / rel_path).resolve()
        # Ensure resolved path is within cwd
        try:
            resolved.relative_to(self.cwd)
        except ValueError:
            raise ValueError(f"Path '{rel_path}' is outside the project root")
        return resolved

    def list_dir(self, rel_path: str | None) -> list[dict]:
        """List immediate children of a directory.

        Returns list of dicts with keys: name, path, type, size (files only), modified.
        """
        target = self._resolve(rel_path)
        if not target.exists():
            raise FileNotFoundError(f"Directory not found: {rel_path}")
        if not target.is_dir():
            raise NotADirectoryError(f"Not a directory: {rel_path}")

        entries = []
        for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            # Skip hidden files/dirs
            if item.name.startswith("."):
                continue
            rel = str(item.relative_to(self.cwd)).replace("\\", "/")
            entry: dict = {
                "name": item.name,
                "path": rel,
                "type": "dir" if item.is_dir() else "file",
            }
            try:
                entry["modified"] = datetime.fromtimestamp(
                    item.stat().st_mtime, tz=timezone.utc
                ).isoformat()
            except OSError:
                pass
            if item.is_file():
                try:
                    entry["size"] = item.stat().st_size
                except OSError:
                    entry["size"] = 0
            entries.append(entry)
        return entries

    def read_file(self, rel_path: str) -> dict:
        """Read file content. Returns dict with content, language, size, modified."""
        target = self._resolve(rel_path)
        if not target.exists():
            raise FileNotFoundError(f"File not found: {rel_path}")
        if not target.is_file():
            raise IsADirectoryError(f"Not a file: {rel_path}")
        if _is_binary(target.name):
            raise ValueError(f"Binary file, cannot preview: {rel_path}")

        content = target.read_text(encoding="utf-8")
        stat = target.stat()
        return {
            "content": content,
            "language": _infer_language(target.name),
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        }

    def write_file(self, rel_path: str, content: str) -> bool:
        """Write content to a file, creating parent dirs if needed."""
        target = self._resolve(rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return True

    def search(self, query: str) -> list[dict]:
        """Search files by name (case-insensitive substring match)."""
        if not query:
            return []
        q = query.lower()
        results = []
        for item in self.cwd.rglob("*"):
            if item.is_file() and q in item.name.lower():
                rel = str(item.relative_to(self.cwd)).replace("\\", "/")
                results.append({
                    "name": item.name,
                    "path": rel,
                    "type": "file",
                })
                if len(results) >= 50:
                    break
        return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd D:\space\labspace\ai_codeagent && python -m pytest tests/test_file_browser.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add agentcore/file_browser.py tests/test_file_browser.py
git commit -m "feat: add FileBrowserHandler — list, read, write, search project files"
```

---

## Task 2: Backend — Wire FileBrowserHandler into ws_server

**Files:**
- Modify: `agentcore/ws_server.py` (lines 721-1165, the `_handle_client` function)

- [ ] **Step 1: Add FileBrowserHandler import at top of ws_server.py**

At the top of `agentcore/ws_server.py`, after the existing imports (around line 16), add:

```python
from agentcore.file_browser import FileBrowserHandler
```

- [ ] **Step 2: Add file browser message handlers in _handle_client**

In `agentcore/ws_server.py`, inside `_handle_client()`, after the `elif msg_type == "list_all_sessions":` block (after line ~1162) and before `elif msg_type == "shutdown":` (line ~1164), insert:

```python
            elif msg_type == "file_list":
                cwd = str(session_mgr._config.cwd or Path.cwd())
                fb = FileBrowserHandler(cwd)
                path = msg.get("path")
                entries = fb.list_dir(path)
                request_id = msg.get("request_id", "")
                await websocket.send(json.dumps({
                    "type": "file_list",
                    "path": path or "",
                    "entries": entries,
                    "request_id": request_id,
                }, ensure_ascii=False))

            elif msg_type == "file_read":
                cwd = str(session_mgr._config.cwd or Path.cwd())
                fb = FileBrowserHandler(cwd)
                file_path = msg.get("path", "")
                request_id = msg.get("request_id", "")
                try:
                    result = fb.read_file(file_path)
                    result["type"] = "file_read"
                    result["path"] = file_path
                    result["request_id"] = request_id
                    await websocket.send(json.dumps(result, ensure_ascii=False))
                except (FileNotFoundError, IsADirectoryError, ValueError) as e:
                    await websocket.send(json.dumps({
                        "type": "file_read",
                        "path": file_path,
                        "request_id": request_id,
                        "error": str(e),
                    }, ensure_ascii=False))

            elif msg_type == "file_write":
                cwd = str(session_mgr._config.cwd or Path.cwd())
                fb = FileBrowserHandler(cwd)
                file_path = msg.get("path", "")
                content = msg.get("content", "")
                request_id = msg.get("request_id", "")
                try:
                    fb.write_file(file_path, content)
                    await websocket.send(json.dumps({
                        "type": "file_write",
                        "path": file_path,
                        "success": True,
                        "request_id": request_id,
                    }, ensure_ascii=False))
                except Exception as e:
                    await websocket.send(json.dumps({
                        "type": "file_write",
                        "path": file_path,
                        "success": False,
                        "error": str(e),
                        "request_id": request_id,
                    }, ensure_ascii=False))

            elif msg_type == "file_search":
                cwd = str(session_mgr._config.cwd or Path.cwd())
                fb = FileBrowserHandler(cwd)
                query = msg.get("query", "")
                request_id = msg.get("request_id", "")
                results = fb.search(query)
                await websocket.send(json.dumps({
                    "type": "file_search",
                    "results": results,
                    "request_id": request_id,
                }, ensure_ascii=False))
```

- [ ] **Step 3: Verify server starts without errors**

Run: `cd D:\space\labspace\ai_codeagent && python -c "from agentcore.ws_server import _handle_client; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add agentcore/ws_server.py
git commit -m "feat: wire file browser message types into ws_server"
```

---

## Task 3: Frontend — Install CodeMirror 6 dependencies

**Files:**
- Modify: `ui/package.json`

- [ ] **Step 1: Install CodeMirror packages**

Run: `cd D:\space\labspace\ai_codeagent\ui && npm install @codemirror/view @codemirror/state @codemirror/language @codemirror/lang-python @codemirror/lang-javascript @codemirror/lang-html @codemirror/lang-css @codemirror/lang-json @codemirror/lang-markdown @codemirror/lang-rust @codemirror/lang-yaml @codemirror/theme-one-dark @codemirror/commands @codemirror/search @codemirror/autocomplete`

- [ ] **Step 2: Verify installation**

Run: `cd D:\space\labspace\ai_codeagent\ui && npm ls @codemirror/view`
Expected: Shows version without errors

- [ ] **Step 3: Commit**

```bash
git add ui/package.json ui/package-lock.json
git commit -m "feat: add CodeMirror 6 dependencies for file browser"
```

---

## Task 4: Frontend — fileBrowser Pinia Store

**Files:**
- Create: `ui/src/stores/fileBrowser.ts`
- Modify: `ui/src/stores/chat.ts` (add inputText ref and insertToInput)

- [ ] **Step 1: Add inputText and insertToInput to chat store**

In `ui/src/stores/chat.ts`, add a new ref and function inside the `defineStore` callback, after the existing refs (after line 41) and before the first function:

```typescript
  // Shared input text for cross-component insertion (e.g. file browser → input bar)
  const inputText = ref('');
```

Add function before `return`:

```typescript
  function insertToInput(text: string) {
    inputText.value += (inputText.value ? ' ' : '') + text;
  }
```

Add to the return statement:

```typescript
    inputText,
    // ... existing returns
    insertToInput,
```

- [ ] **Step 2: Create fileBrowser store**

Create `ui/src/stores/fileBrowser.ts`:

```typescript
// ui/src/stores/fileBrowser.ts
import { ref, computed } from 'vue';
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

  // Pending request tracking
  private pendingRequests = new Map<string, {
    resolve: (data: any) => void;
    reject: (err: Error) => void;
    timer: ReturnType<typeof setTimeout>;
  }>();
  private requestIdCounter = 0;

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

  // ── Actions ──────────────────────────────────────────

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
    if (openEditors.value.has(path)) {
      return; // Already open
    }
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
    } catch (e: any) {
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

  // ── Internal ─────────────────────────────────────────

  function _insertChildren(dirPath: string, children: TreeNode[]) {
    const parts = dirPath.split('/');
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
```

- [ ] **Step 3: Verify TypeScript compilation**

Run: `cd D:\space\labspace\ai_codeagent\ui && npx vue-tsc --noEmit 2>&1 | head -20`
Expected: No errors in the new file

- [ ] **Step 4: Commit**

```bash
git add ui/src/stores/fileBrowser.ts ui/src/stores/chat.ts
git commit -m "feat: add fileBrowser Pinia store and chat store insertToInput"
```

---

## Task 5: Frontend — Wire file browser events in App.vue

**Files:**
- Modify: `ui/src/App.vue` (lines 74-247, the `onMounted` block)

- [ ] **Step 1: Add file browser event listeners in onMounted**

In `ui/src/App.vue`, add the import at the top of `<script setup>`:

```typescript
import { useFileBrowserStore } from './stores/fileBrowser';
```

Instantiate the store after other store instances (after line 57):

```typescript
const fileBrowserStore = useFileBrowserStore();
```

Inside the `onMounted` callback, after the existing `agentWs.on('agent_list', ...)` block (around line 244), add:

```typescript
  // File browser responses
  agentWs.on('file_list', (d: any) => fileBrowserStore.handleResponse(d));
  agentWs.on('file_read', (d: any) => fileBrowserStore.handleResponse(d));
  agentWs.on('file_write', (d: any) => fileBrowserStore.handleResponse(d));
  agentWs.on('file_search', (d: any) => fileBrowserStore.handleResponse(d));
```

- [ ] **Step 2: Verify compilation**

Run: `cd D:\space\labspace\ai_codeagent\ui && npx vue-tsc --noEmit 2>&1 | head -20`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add ui/src/App.vue
git commit -m "feat: wire file browser WebSocket events in App.vue"
```

---

## Task 6: Frontend — InputBar integration with shared inputText

**Files:**
- Modify: `ui/src/components/InputBar.vue`

- [ ] **Step 1: Read current InputBar.vue**

Read the file to understand its current textarea binding.

- [ ] **Step 2: Bind textarea to chatStore.inputText**

In `ui/src/components/InputBar.vue`, change the textarea to bind to `chatStore.inputText` instead of any local ref. The `v-model` should use `chatStore.inputText`, and the send function should use `chatStore.inputText` as the message source, then clear it via `chatStore.inputText = ''` after sending.

If the textarea currently uses a local ref like `const text = ref('')`, replace it with:

```typescript
const chatStore = useChatStore();
```

And change the textarea `v-model` to `chatStore.inputText`.

- [ ] **Step 3: Verify the app still compiles and the input bar works**

Run: `cd D:\space\labspace\ai_codeagent\ui && npx vue-tsc --noEmit 2>&1 | head -20`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add ui/src/components/InputBar.vue
git commit -m "refactor: bind InputBar textarea to shared chatStore.inputText"
```

---

## Task 7: Frontend — FileTreePanel Component

**Files:**
- Create: `ui/src/components/FileTreePanel.vue`

- [ ] **Step 1: Create FileTreePanel.vue**

Create `ui/src/components/FileTreePanel.vue`:

```vue
<template>
  <div class="flex flex-col h-full bg-surface-1 border-r border-border-default select-none" :style="{ width: panelWidth + 'px', minWidth: '200px', maxWidth: '400px' }">
    <!-- Tab bar -->
    <div class="flex items-center border-b border-border-default bg-surface-2 text-xs overflow-x-auto shrink-0">
      <button
        class="px-3 py-1.5 border-b-2 whitespace-nowrap cursor-pointer transition-colors"
        :class="fileBrowser.activeTab === 'tree' ? 'border-accent text-text-primary' : 'border-transparent text-text-muted hover:text-text-secondary'"
        @click="fileBrowser.activeTab = 'tree'"
      >文件树</button>
      <button
        v-if="fileBrowser.previewPath"
        class="px-3 py-1.5 border-b-2 whitespace-nowrap cursor-pointer transition-colors flex items-center gap-1"
        :class="fileBrowser.activeTab === fileBrowser.previewPath ? 'border-accent text-text-primary' : 'border-transparent text-text-muted hover:text-text-secondary'"
        @click="fileBrowser.activeTab = fileBrowser.previewPath!"
      >
        <span class="font-mono truncate max-w-[100px]">{{ fileName(fileBrowser.previewPath) }}</span>
        <span class="text-text-muted hover:text-text-primary" @click.stop="fileBrowser.closePreview()">✕</span>
      </button>
    </div>

    <!-- File tree view -->
    <div v-show="fileBrowser.activeTab === 'tree'" class="flex flex-col flex-1 overflow-hidden">
      <!-- Search box -->
      <div class="px-2 py-1.5 border-b border-border-subtle shrink-0">
        <input
          v-model="searchInput"
          class="w-full bg-surface-0 border border-border-default rounded px-2 py-1 text-xs text-text-primary outline-none focus:border-accent"
          placeholder="搜索文件..."
          @input="onSearchInput"
        />
      </div>

      <!-- Search results -->
      <div v-if="searchInput && fileBrowser.searchResults.length > 0" class="flex-1 overflow-y-auto py-1">
        <div
          v-for="item in fileBrowser.searchResults"
          :key="item.path"
          class="flex items-center gap-1.5 px-3 py-1 cursor-pointer text-xs hover:bg-surface-2"
          :class="fileBrowser.selectedFile === item.path ? 'bg-accent-subtle text-accent' : 'text-text-secondary'"
          @click="onFileClick(item)"
          @dblclick="onFileDblClick(item)"
        >
          <span class="shrink-0">{{ fileIcon(item.name) }}</span>
          <span class="truncate font-mono">{{ item.name }}</span>
          <span class="ml-auto text-text-muted truncate max-w-[80px]">{{ item.path }}</span>
        </div>
      </div>

      <!-- Empty search -->
      <div v-else-if="searchInput && fileBrowser.searchResults.length === 0" class="flex-1 flex items-center justify-center text-text-muted text-xs py-8">
        无搜索结果
      </div>

      <!-- Tree -->
      <div v-else class="flex-1 overflow-y-auto py-1">
        <div v-if="fileBrowser.tree.length === 0 && !fileBrowser.loading" class="flex items-center justify-center text-text-muted text-xs py-8">
          暂无文件
        </div>
        <template v-for="node in fileBrowser.tree" :key="node.path">
          <TreeNodeItem
            :node="node"
            :depth="0"
            :selected="fileBrowser.selectedFile"
            :expanded="fileBrowser.expandedDirs.has(node.path)"
            @toggle="onToggleDir"
            @select="onFileClick"
            @dblclick="onFileDblClick"
            @contextmenu.prevent="onContextMenu($event, node)"
          />
        </template>
      </div>
    </div>

    <!-- Preview view -->
    <div v-show="fileBrowser.activeTab !== 'tree' && fileBrowser.previewPath" class="flex flex-col flex-1 overflow-hidden">
      <!-- Preview breadcrumb -->
      <div class="px-2 py-1 text-[10px] text-text-muted border-b border-border-subtle truncate shrink-0">
        {{ fileBrowser.previewPath }}
      </div>
      <!-- Preview content -->
      <div class="flex-1 overflow-auto p-2">
        <div v-if="fileBrowser.error" class="text-xs text-danger p-2">{{ fileBrowser.error }}</div>
        <pre v-else class="font-mono text-[11px] leading-relaxed text-text-primary whitespace-pre-wrap break-all">{{ fileBrowser.previewContent }}</pre>
      </div>
      <!-- Preview action bar -->
      <div class="flex gap-1.5 px-2 py-1.5 border-t border-border-default shrink-0">
        <button class="bg-accent text-white text-xs px-3 py-1 rounded cursor-pointer hover:bg-accent-hover" @click="sendToAgent">→ Agent</button>
        <button class="bg-surface-3 text-text-secondary text-xs px-3 py-1 rounded cursor-pointer hover:bg-surface-4" @click="openInEditor">⛶ 展开</button>
      </div>
    </div>

    <!-- Resize handle -->
    <div
      class="absolute top-0 right-0 w-1 h-full cursor-col-resize hover:bg-accent/30"
      @mousedown.prevent="startResize"
    ></div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useFileBrowserStore, type TreeNode } from '../stores/fileBrowser';
import { useChatStore } from '../stores/chat';
import TreeNodeItem from './TreeNodeItem.vue';

const fileBrowser = useFileBrowserStore();
const chatStore = useChatStore();

const panelWidth = ref(260);
const searchInput = ref('');
let searchTimer: ReturnType<typeof setTimeout> | null = null;

function fileName(path: string) {
  return path.split('/').pop() || path;
}

function fileIcon(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase() || '';
  const icons: Record<string, string> = {
    py: '🐍', ts: '🔷', js: '🔷', vue: '💚', html: '🌐', css: '🎨',
    json: '📋', md: '📝', yaml: '📋', yml: '📋', toml: '📋',
    rs: '🦀', go: '🔵', java: '☕', sh: '⚙️', bat: '⚙️',
    txt: '📄', sql: '🗃️', xml: '🌐',
  };
  return icons[ext] || '📄';
}

function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    fileBrowser.searchFiles(searchInput.value);
  }, 300);
}

function onToggleDir(node: TreeNode) {
  if (node.type !== 'dir') return;
  if (fileBrowser.expandedDirs.has(node.path)) {
    fileBrowser.expandedDirs.delete(node.path);
  } else {
    if (!node.loaded) {
      fileBrowser.loadDir(node.path);
    } else {
      fileBrowser.expandedDirs = new Set([...fileBrowser.expandedDirs, node.path]);
    }
  }
}

function onFileClick(node: TreeNode) {
  if (node.type === 'dir') {
    onToggleDir(node);
  } else {
    fileBrowser.selectFile(node.path);
  }
}

function onFileDblClick(node: TreeNode) {
  if (node.type === 'file') {
    fileBrowser.openEditor(node.path);
  }
}

function sendToAgent() {
  if (fileBrowser.previewPath) {
    chatStore.insertToInput(`@file:${fileBrowser.previewPath}`);
  }
}

function openInEditor() {
  if (fileBrowser.previewPath) {
    fileBrowser.openEditor(fileBrowser.previewPath);
  }
}

function onContextMenu(event: MouseEvent, node: TreeNode) {
  // Context menu placeholder — can be enhanced later
}

function startResize(e: MouseEvent) {
  const startX = e.clientX;
  const startWidth = panelWidth.value;
  function onMove(ev: MouseEvent) {
    panelWidth.value = Math.min(400, Math.max(200, startWidth + (ev.clientX - startX)));
  }
  function onUp() {
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
  }
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
}
</script>
```

- [ ] **Step 2: Create TreeNodeItem sub-component**

Create `ui/src/components/TreeNodeItem.vue`:

```vue
<template>
  <div>
    <div
      class="flex items-center gap-1 cursor-pointer text-xs py-0.5 pr-2 transition-colors"
      :style="{ paddingLeft: depth * 14 + 8 + 'px' }"
      :class="node.type === 'file' && selected === node.path ? 'bg-accent-subtle text-accent' : 'text-text-secondary hover:bg-surface-2'"
      @click="$emit('select', node)"
      @dblclick="$emit('dblclick', node)"
      @contextmenu.prevent="$emit('contextmenu', $event, node)"
    >
      <!-- Expand toggle for dirs -->
      <span v-if="node.type === 'dir'" class="shrink-0 w-3 text-center text-text-muted">
        {{ expanded ? '▾' : '▸' }}
      </span>
      <span v-else class="shrink-0 w-3"></span>
      <!-- Icon -->
      <span class="shrink-0">{{ node.type === 'dir' ? (expanded ? '📂' : '📁') : fileIcon(node.name) }}</span>
      <!-- Name -->
      <span class="truncate font-mono">{{ node.name }}</span>
    </div>
    <!-- Children (expanded) -->
    <div v-if="node.type === 'dir' && expanded && node.children">
      <div v-if="!node.loaded" class="text-text-muted text-[10px] pl-4 py-0.5">加载中...</div>
      <TreeNodeItem
        v-for="child in node.children"
        :key="child.path"
        :node="child"
        :depth="depth + 1"
        :selected="selected"
        :expanded="expandedDirs.has(child.path)"
        @select="$emit('select', $event)"
        @dblclick="$emit('dblclick', $event)"
        @contextmenu="$emit('contextmenu', $event, $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { TreeNode } from '../stores/fileBrowser';

const props = defineProps<{
  node: TreeNode;
  depth: number;
  selected: string | null;
  expanded: boolean;
}>();

defineEmits<{
  select: [node: TreeNode];
  dblclick: [node: TreeNode];
  contextmenu: [event: MouseEvent, node: TreeNode];
}>();

import { useFileBrowserStore } from '../stores/fileBrowser';
const fileBrowser = useFileBrowserStore();
const expandedDirs = fileBrowser.expandedDirs;

function fileIcon(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase() || '';
  const icons: Record<string, string> = {
    py: '🐍', ts: '🔷', js: '🔷', vue: '💚', html: '🌐', css: '🎨',
    json: '📋', md: '📝', yaml: '📋', yml: '📋', toml: '📋',
    rs: '🦀', go: '🔵', java: '☕', sh: '⚙️', bat: '⚙️',
    txt: '📄', sql: '🗃️', xml: '🌐',
  };
  return icons[ext] || '📄';
}
</script>
```

- [ ] **Step 3: Verify compilation**

Run: `cd D:\space\labspace\ai_codeagent\ui && npx vue-tsc --noEmit 2>&1 | head -20`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add ui/src/components/FileTreePanel.vue ui/src/components/TreeNodeItem.vue
git commit -m "feat: add FileTreePanel and TreeNodeItem components"
```

---

## Task 8: Frontend — CodeEditorDialog Component

**Files:**
- Create: `ui/src/components/CodeEditorDialog.vue`

- [ ] **Step 1: Create CodeEditorDialog.vue**

Create `ui/src/components/CodeEditorDialog.vue`:

```vue
<template>
  <teleport to="body">
    <div v-for="[path, editor] in fileBrowser.openEditors" :key="path">
      <div
        class="fixed bg-surface-1 border border-border-default shadow-dialog rounded-lg flex flex-col overflow-hidden z-50"
        :style="{ left: dialogX + 'px', top: dialogY + 'px', width: dialogWidth + 'px', height: dialogHeight + 'px' }"
      >
        <!-- Title bar -->
        <div
          class="flex items-center justify-between px-3 py-2 bg-surface-2 border-b border-border-default cursor-move shrink-0"
          @mousedown.prevent="startDrag($event, path)"
        >
          <div class="flex items-center gap-2 min-w-0">
            <span class="font-mono text-sm text-text-primary truncate">{{ path.split('/').pop() }}</span>
            <span class="text-[10px] text-text-muted truncate">{{ path }}</span>
            <span class="text-[10px] text-text-muted">{{ formatSize(editor.size) }}</span>
          </div>
          <div class="flex items-center gap-1.5 shrink-0">
            <button
              class="bg-accent text-white text-xs px-2.5 py-0.5 rounded cursor-pointer hover:bg-accent-hover"
              @click="sendToAgent(path)"
            >→ Agent</button>
            <button
              class="text-xs px-2.5 py-0.5 rounded cursor-pointer"
              :class="editor.dirty ? 'bg-success text-white hover:bg-success/90' : 'bg-surface-3 text-text-secondary hover:bg-surface-4'"
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
        <div class="flex-1 overflow-hidden" :ref="(el) => setEditorContainer(el, path)"></div>

        <!-- Dirty indicator -->
        <div v-if="editor.dirty" class="px-3 py-1 text-[10px] text-warning bg-warning-subtle border-t border-border-subtle shrink-0">
          未保存更改
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { ref, watch, onUnmounted, nextTick } from 'vue';
import { useFileBrowserStore, type EditorState } from '../stores/fileBrowser';
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

const dialogX = ref(120);
const dialogY = ref(60);
const dialogWidth = ref(640);
const dialogHeight = ref(480);

const editorViews = new Map<string, EditorView>();
const containerRefs = new Map<string, HTMLElement>();

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
  containerRefs.set(path, el as HTMLElement);
  const editor = fileBrowser.openEditors.get(path);
  if (editor && !editorViews.has(path)) {
    createEditor(path, editor, el as HTMLElement);
  }
}

function createEditor(path: string, editor: EditorState, container: HTMLElement) {
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
        run: () => {
          saveEditor(path);
          return true;
        },
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
  const editor = fileBrowser.openEditors.get(path);
  if (view && editor) {
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

// Clean up editor views when editors are closed
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
  for (const view of editorViews.values()) {
    view.destroy();
  }
  editorViews.clear();
});
</script>
```

- [ ] **Step 2: Verify compilation**

Run: `cd D:\space\labspace\ai_codeagent\ui && npx vue-tsc --noEmit 2>&1 | head -20`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add ui/src/components/CodeEditorDialog.vue
git commit -m "feat: add CodeEditorDialog with CodeMirror 6 integration"
```

---

## Task 9: Frontend — Integrate into App.vue layout

**Files:**
- Modify: `ui/src/App.vue`

- [ ] **Step 1: Add imports for new components**

In `ui/src/App.vue` `<script setup>`, add after the existing imports (around line 52):

```typescript
import FileTreePanel from './components/FileTreePanel.vue';
import CodeEditorDialog from './components/CodeEditorDialog.vue';
import { useFileBrowserStore } from './stores/fileBrowser';
```

And after the store instantiations (around line 57):

```typescript
const fileBrowserStore = useFileBrowserStore();
```

- [ ] **Step 2: Add file browser toggle button to header**

In the header area (around line 4-15), add a file browser toggle button after the sidebar toggle button:

```html
<button class="bg-transparent border-none text-lg cursor-pointer p-1 text-text-primary" @click="fileBrowserStore.togglePanel()">📁</button>
```

- [ ] **Step 3: Add FileTreePanel to the layout**

In the main flex container (around line 17-26), add the FileTreePanel between the sidebar and the chat area:

```html
      <!-- File browser panel -->
      <FileTreePanel v-if="fileBrowserStore.panelVisible" />
```

Insert this right after the SessionList div (after line 20) and before the main content div.

- [ ] **Step 4: Add CodeEditorDialog at the bottom of the template**

After the dialogs section (around line 32), add:

```html
    <CodeEditorDialog />
```

- [ ] **Step 5: Verify full app compiles**

Run: `cd D:\space\labspace\ai_codeagent\ui && npx vue-tsc --noEmit 2>&1 | head -20`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add ui/src/App.vue
git commit -m "feat: integrate FileTreePanel and CodeEditorDialog into App layout"
```

---

## Task 10: Integration Test — Manual smoke test

**Files:** None (manual testing)

- [ ] **Step 1: Start backend**

Run: `cd D:\space\labspace\ai_codeagent && python -m agentcore.main --ws --port 18765`

- [ ] **Step 2: Start frontend dev server**

Run: `cd D:\space\labspace\ai_codeagent\ui && npm run dev`

- [ ] **Step 3: Verify file browser functionality**

Checklist:
1. Click 📁 button in header → file tree panel appears
2. Root directory files/folders are listed
3. Click a folder → expands, loads children
4. Click a file → tab switches to preview with content
5. Double-click a file → CodeEditorDialog pops up with syntax highlighting
6. Edit file in CodeEditorDialog → "未保存更改" indicator appears
7. Ctrl+S → saves file
8. Click "→ Agent" → `@file:path` appears in input bar
9. Search box → type query, results appear
10. Click 📁 again → panel hides

- [ ] **Step 4: Fix any issues found during smoke test**

Address bugs discovered during testing.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "fix: address smoke test issues for file browser"
```

---

## Self-Review

### Spec Coverage

| Spec Requirement | Task |
|---|---|
| FileBrowserHandler (list, read, write, search) | Task 1 |
| WebSocket message types (file_list, file_read, file_write, file_search) | Task 2 |
| Pinia store (tree, preview, editors, actions) | Task 4 |
| CodeMirror 6 dependencies | Task 3 |
| IconBar toggle button | Task 9 |
| FileTreePanel (tree, tabs, search) | Task 7 |
| TreeNodeItem (recursive tree) | Task 7 |
| CodeEditorDialog (drag, save, send-to-agent) | Task 8 |
| App.vue integration | Task 9 |
| InputBar shared inputText | Task 6 |
| Path safety (traversal prevention) | Task 1 |
| Binary file detection | Task 1 |
| Language inference | Task 1 |
| Lazy-load directories | Task 7 |
| Debounced search | Task 7 |
| Send to Agent | Task 7, 8 |
| Drag-move editor dialog | Task 8 |
| Ctrl+S save | Task 8 |

### Placeholder Scan

No TBD, TODO, or placeholder steps found.

### Type Consistency

- `TreeNode` interface defined in `fileBrowser.ts`, used in `FileTreePanel.vue` and `TreeNodeItem.vue`
- `EditorState` interface defined in `fileBrowser.ts`, used in `CodeEditorDialog.vue`
- WebSocket message types match between Python handler and TypeScript store
- `request_id` pattern consistent: `_nextRequestId()` generates, `handleResponse()` consumes
