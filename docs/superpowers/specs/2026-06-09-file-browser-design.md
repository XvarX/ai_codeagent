# 文件浏览器设计文档

## 概述

为 AI Code Agent 桌面应用添加文件浏览器功能，让用户在 GUI 中浏览项目文件树、预览代码、编辑文件、发送文件给 Agent。

## 背景

- 项目使用 Vue 3 + Tauri 2 + Tailwind CSS 前端，Python 后端通过 WebSocket 通信
- 当前布局：左侧 SessionList | 中间 ChatView + 底部 AgentPanel | 右侧 DebugDrawer
- Session 后端可能运行在不同机器上，文件操作必须走 WebSocket 后端而非 Tauri 原生命令

## 技术选型

| 决策 | 选择 | 理由 |
|------|------|------|
| 文件系统通信 | WebSocket → Python 后端 | Session 后端可能在不同机器上 |
| 代码编辑器 | CodeMirror 6 | 轻量、性能好、语法高亮可扩展 |
| UI 布局 | 左侧面板 + Tab 预览 + 双击弹出独立编辑框 | 类似 VS Code 的交互模式 |

## 架构

### 数据流

```
前端组件 → WebSocket JSON → ws_server.py → FileBrowserHandler → os/pathlib → 文件系统
```

### 新增文件

| 文件 | 职责 |
|------|------|
| `agentcore/file_browser.py` | 后端文件浏览器处理器（目录列表、读文件、写文件、搜索） |
| `ui/src/stores/fileBrowser.ts` | Pinia store，管理文件浏览器状态 |
| `ui/src/components/FileTreePanel.vue` | 文件树面板组件（含 Tab 切换） |
| `ui/src/components/CodeEditorDialog.vue` | 独立代码编辑框组件（CodeMirror 6） |

### 修改文件

| 文件 | 改动 |
|------|------|
| `agentcore/ws_server.py` | 新增 4 个消息类型处理 |
| `ui/src/App.vue` | 集成图标栏、FileTreePanel、CodeEditorDialog |
| `ui/src/services/agentWs.ts` | 新增文件浏览器相关的事件监听 |
| `ui/src/stores/chat.ts` | 新增 insertToInput 方法（接收文件路径） |
| `ui/package.json` | 添加 codemirror 依赖 |

## 后端 WebSocket API

### 新增消息类型

#### `file_list` — 列目录内容

请求：
```json
{ "type": "file_list", "path": "agentcore", "request_id": "..." }
```

响应：
```json
{
  "type": "file_list",
  "path": "agentcore",
  "entries": [
    { "name": "agent.py", "path": "agentcore/agent.py", "type": "file", "size": 4200, "modified": "2026-06-09T10:30:00" },
    { "name": "providers", "path": "agentcore/providers", "type": "dir", "modified": "2026-06-08T15:00:00" }
  ],
  "request_id": "..."
}
```

- `path` 可选，默认为 Agent 的 cwd（项目根目录）
- 返回一级子项，不做递归（懒加载）

#### `file_read` — 读取文件内容

请求：
```json
{ "type": "file_read", "path": "agentcore/agent.py", "request_id": "..." }
```

响应：
```json
{
  "type": "file_read",
  "path": "agentcore/agent.py",
  "content": "class Agent:\n    ...",
  "language": "python",
  "size": 4200,
  "modified": "2026-06-09T10:30:00",
  "request_id": "..."
}
```

- `language` 根据文件扩展名推断
- 二进制文件返回 `{ "type": "file_read", "error": "binary_file" }`

#### `file_write` — 写入文件

请求：
```json
{ "type": "file_write", "path": "agentcore/agent.py", "content": "...", "request_id": "..." }
```

响应：
```json
{ "type": "file_write", "path": "agentcore/agent.py", "success": true, "request_id": "..." }
```

#### `file_search` — 按名称搜索文件

请求：
```json
{ "type": "file_search", "query": "agent", "request_id": "..." }
```

响应：
```json
{
  "type": "file_search",
  "results": [
    { "name": "agent.py", "path": "agentcore/agent.py", "type": "file" },
    { "name": "agent_tool.py", "path": "agentcore/tools/agent_tool.py", "type": "file" }
  ],
  "request_id": "..."
}
```

### FileBrowserHandler

```python
class FileBrowserHandler:
    def __init__(self, cwd: str):
        self.cwd = cwd

    def list_dir(self, rel_path: str | None) -> list[FileEntry]: ...
    def read_file(self, rel_path: str) -> FileContent: ...
    def write_file(self, rel_path: str, content: str) -> bool: ...
    def search(self, query: str) -> list[FileEntry]: ...
```

- 所有路径相对于 Agent 的 cwd
- 安全校验：禁止路径逃逸（`..` 到 cwd 之外）
- 二进制检测：通过文件扩展名或 magic bytes 判断

## 前端 Store — `fileBrowser.ts`

```typescript
interface TreeNode {
  name: string
  path: string           // 相对路径
  type: 'file' | 'dir'
  size?: number
  modified?: string
  children?: TreeNode[]  // 仅 dir，懒加载
  loaded?: boolean       // 目录是否已加载子项
}

interface EditorState {
  path: string
  content: string
  language: string
  modified: boolean      // 本地是否有未保存修改
}

// State
{
  tree: TreeNode[]                    // 根目录内容
  expandedDirs: Set<string>           // 已展开的目录
  selectedFile: string | null         // 当前选中文件路径
  previewContent: string | null       // Tab 预览内容
  previewPath: string | null
  openEditors: Map<string, EditorState>  // 独立编辑框（可多开）
  panelVisible: boolean               // 文件面板是否可见
  activeTab: 'tree' | string          // 'tree' 或文件路径
}
```

### Actions

- `loadDir(path?)` — 请求 `file_list`，填充 tree
- `selectFile(path)` — 请求 `file_read`，填充 preview
- `openEditor(path)` — 请求 `file_read`，打开独立编辑框
- `saveFile(path, content)` — 请求 `file_write`
- `searchFiles(query)` — 请求 `file_search`
- `sendToAgent(path)` — 将路径插入 ChatStore 的输入框

## 前端组件

### IconBar 集成

在 App.vue header 左侧添加图标按钮组：
- Sessions（现有侧边栏切换）
- Files（切换 FileTreePanel 可见性）
- Settings（现有 ConfigDialog）

### FileTreePanel

- 位于左侧，与 ChatView 平行，可通过 IconBar 切换显示/隐藏
- 面板宽度可拖拽调整（200-400px，默认 260px）
- **Tab 栏**：默认「文件树」Tab，单击文件后新增文件名 Tab
- **文件树区域**：
  - 懒加载目录（点击文件夹触发 `loadDir`）
  - 文件图标按类型区分（文件夹、.py、.ts、.vue、.md 等）
  - 当前选中文件高亮
- **预览区域**（Tab 切换到文件时显示）：
  - 只读代码预览，带行号
  - 底部操作栏：「→ Agent」「⛶ 展开」
- 面板底部搜索框：输入即搜索（debounce 300ms）

### CodeEditorDialog

- 基于 CodeMirror 6 的独立浮动窗口
- 可拖拽移动（通过标题栏拖拽）
- **标题栏**：文件名、路径面包屑、行数、大小、操作按钮（发送给 Agent、保存、关闭）
- **编辑区域**：CodeMirror 6 实例，语法高亮根据 `language` 字段自动切换
- **保存**：Ctrl+S 或点击保存按钮，调用 `file_write`
- **发送给 Agent**：将 `@file:agentcore/agent.py` 插入聊天输入框并聚焦

### 交互映射

| 操作 | 行为 |
|------|------|
| 点击 IconBar 📁 | 切换 FileTreePanel 显示/隐藏 |
| 点击文件夹 | 懒加载展开/收缩 |
| 单击文件 | Tab 切换到只读预览 |
| 双击文件 | 弹出独立 CodeEditorDialog |
| Ctrl+S（编辑框内） | 保存文件 |
| 右键文件 | 上下文菜单：复制路径 / 发送给 Agent / 删除 |
| 搜索框输入 | debounce 300ms 后搜索文件 |

## 错误处理

| 场景 | 处理 |
|------|------|
| 二进制文件 | 预览区显示"不支持预览此文件类型" |
| 后端断连 | 文件面板显示"后端连接断开"，禁用所有文件操作 |
| 保存冲突 | 文件在编辑期间被 Agent 修改时，保存提示"文件已被修改，是否覆盖？" |
| 路径逃逸 | 后端拒绝 cwd 之外的路径访问 |
| 权限不足 | 后端返回错误，前端显示提示 |

## CodeMirror 6 依赖

```json
{
  "@codemirror/view": "^6.x",
  "@codemirror/state": "^6.x",
  "@codemirror/lang-python": "^6.x",
  "@codemirror/lang-javascript": "^6.x",
  "@codemirror/lang-html": "^6.x",
  "@codemirror/lang-css": "^6.x",
  "@codemirror/lang-json": "^6.x",
  "@codemirror/lang-markdown": "^6.x",
  "@codemirror/lang-rust": "^6.x",
  "@codemirror/theme-one-dark": "^6.x",
  "@codemirror/commands": "^6.x",
  "@codemirror/search": "^6.x"
}
```

## 不在范围内

- Git 状态集成（文件变更标记）
- 多 Tab 编辑器（一次只打开一个独立编辑框）
- 文件拖拽上传
- 终端/控制台集成
