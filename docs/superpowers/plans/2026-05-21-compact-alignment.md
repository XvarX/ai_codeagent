# Compact 源码对齐实施计划

基于 Claude Code 源码分析，对齐三层压缩。

---

### Task 1: 工具加 maxResultSizeChars + 单条截断

**改 `tools/base.py`**：Tool 基类加 `max_result_chars` 属性（默认 100000）

**改各工具文件**：
- `BashTool`: 不设（继承默认 100000）
- `FileReadTool`: `max_result_chars = None`（不截断）
- `GrepTool`: `max_result_chars = 20000`
- `GlobTool`: `max_result_chars = 100000`
- `FileEditTool`: `max_result_chars = 100000`
- `FileWriteTool`: `max_result_chars = 100000`

**改 `agent.py`**：工具结果追加到消息历史前，检查是否超过 `max_result_chars`，超过则截断尾部并加 `... [truncated]` 标记

---

### Task 2: 修复 MicroCompact 触发条件

**改 `compact/microCompact.py`**：
- 触发条件从"每轮"改为"compactable 工具结果超过 5 个时"
- 保留最近 5 个，清旧的内容为 `[Old tool result — content cleared]`

**同步 `agent.py`**：microCompact 调用不变（仍在每轮 LLM 调用前执行，但内部有数量门槛）

---

### Task 3: AutoCompact 后回注最近文件

**改 `compact/compact.py`**：
- `compact_conversation()` 完成后，扫描 `messages_to_keep`(preserved) 中的 FileRead 调用
- 收集最近访问的文件路径，去掉已在 preserved 中出现的
- 按出现顺序取最后 3 个
- 重新读取，每个最多 2000 字符
- 作为额外消息附加到 `summary_messages` 中
- 跳过 `.yaml`, `.md`, plan 文件

---

### Task 4: agent.py 中 compact pipeline 清理

- 去掉冗余日志
- 微压缩 + 自动压缩的日志输出精简
- `_last_actual_tokens` 追踪保持
