<template>
  <div class="diff-viewer">
    <div class="diff-header" @click="open = !open">
      <span class="arrow">{{ open ? '▼' : '▶' }}</span>
      <span class="filename">{{ filename }}</span>
      <span class="summary">+{{ added }} -{{ removed }}</span>
      <span class="filepath">{{ filePath }}</span>
    </div>
    <div v-if="open" class="diff-body">
      <div class="expand-row">
        <button class="expand-all-btn" @click="expandAll">&#8691; Expand All</button>
      </div>
      <div class="diff-scroll">
        <template v-for="block in resolvedBlocks" :key="block.key">
          <div
            v-if="block.tag === 'fold'"
            class="fold-row"
            @click="openFold(block.key)"
          >
            <span>{{ block.count }} lines unchanged</span>
            <span class="fold-icon">&#8691;</span>
          </div>
          <template v-else>
            <div
              v-for="(row, ri) in blockRows(block)"
              :key="block.key + '-' + ri"
              class="diff-row"
            >
              <div :class="['diff-side', row.oldBgClass]">
                <span class="line-num">{{ row.oldNum }}</span>
                <span class="line-spacer"></span>
                <span :class="['code-text', row.oldColorClass]">{{ row.oldText }}</span>
              </div>
              <div class="diff-divider"></div>
              <div :class="['diff-side', row.newBgClass]">
                <span class="line-num">{{ row.newNum }}</span>
                <span class="line-spacer"></span>
                <span :class="['code-text', row.newColorClass]">{{ row.newText }}</span>
              </div>
            </div>
          </template>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive } from 'vue';
import { diffLines } from 'diff';

interface DiffBlock {
  tag: 'change' | 'equal' | 'fold';
  os: number;
  ns: number;
  ol: string[];
  nl: string[];
  count?: number;
  key: string;
}

interface DiffRow {
  oldNum: string;
  oldText: string;
  oldBgClass: string;
  oldColorClass: string;
  newNum: string;
  newText: string;
  newBgClass: string;
  newColorClass: string;
}

const props = defineProps<{
  filePath: string;
  oldContent: string;
  newContent: string;
}>();

const open = ref(true);
const expandedKeys = reactive(new Set<string>());
let keyCounter = 0;

const filename = computed(() => {
  return props.filePath.replace(/\\/g, '/').split('/').pop() || '';
});

const blocks = computed<DiffBlock[]>(() => {
  return buildDiffBlocks(props.oldContent, props.newContent);
});

const added = computed(() => {
  return blocks.value
    .filter(b => b.tag === 'change')
    .reduce((sum, b) => sum + b.nl.length, 0);
});

const removed = computed(() => {
  return blocks.value
    .filter(b => b.tag === 'change')
    .reduce((sum, b) => sum + b.ol.length, 0);
});

const resolvedBlocks = computed<DiffBlock[]>(() => {
  return blocks.value.map(b => {
    if (b.tag === 'fold' && expandedKeys.has(b.key)) {
      return {
        tag: 'equal',
        os: b.os,
        ns: b.ns,
        ol: [...b.ol],
        nl: [...b.nl],
        key: b.key + '-x',
      } as DiffBlock;
    }
    return b;
  });
});

function buildDiffBlocks(oldText: string, newText: string, ctx: number = 3): DiffBlock[] {
  const oldLines = oldText ? oldText.split('\n') : [];
  const newLines = newText ? newText.split('\n') : [];

  const changes = diffLines(
    oldLines.join('\n'),
    newLines.join('\n'),
    { ignoreNewlineAtEof: true }
  );

  // Convert diff changes to raw blocks with line number tracking
  interface RawBlock {
    tag: 'change' | 'equal';
    os: number;
    ol: string[];
    ns: number;
    nl: string[];
  }
  const raw: RawBlock[] = [];
  let oi = 0;
  let ni = 0;

  for (const ch of changes) {
    const text = ch.value;
    const hasTrailingNewline = text.endsWith('\n');
    const lines = text.split('\n');
    // Remove trailing empty string from split if there was a trailing newline
    if (hasTrailingNewline && lines.length > 1) {
      lines.pop();
    }
    const count = lines.length;

    if (ch.removed) {
      raw.push({ tag: 'change', os: oi, ol: lines, ns: ni, nl: [] });
      oi += count;
    } else if (ch.added) {
      raw.push({ tag: 'change', os: oi, ol: [], ns: ni, nl: lines });
      ni += count;
    } else {
      raw.push({ tag: 'equal', os: oi, ol: lines, ns: ni, nl: lines });
      oi += count;
      ni += count;
    }
  }

  // Merge consecutive changes
  const merged: RawBlock[] = [];
  for (const b of raw) {
    if (b.tag === 'change' && merged.length > 0 && merged[merged.length - 1].tag === 'change') {
      const last = merged[merged.length - 1];
      last.ol = last.ol.concat(b.ol);
      last.nl = last.nl.concat(b.nl);
    } else {
      merged.push({ ...b });
    }
  }

  // Find change indices
  const changeIndices = merged
    .map((b, i) => (b.tag === 'change' ? i : -1))
    .filter(i => i >= 0);
  if (!changeIndices.length) return [];

  // Build result with context folding
  const result: DiffBlock[] = [];
  keyCounter = 0;

  for (let i = 0; i < merged.length; i++) {
    const b = merged[i];
    if (b.tag === 'change') {
      result.push({ ...b, key: `c${keyCounter++}` });
      continue;
    }
    const n = b.ol.length;
    if (n === 0) continue;

    if (i < changeIndices[0]) {
      if (n > ctx) {
        result.push({
          tag: 'fold', os: b.os, ns: b.ns,
          ol: b.ol.slice(0, n - ctx), nl: b.nl.slice(0, n - ctx),
          count: n - ctx, key: `f${keyCounter++}`,
        });
      }
      result.push({
        tag: 'equal',
        os: b.os + Math.max(0, n - ctx),
        ns: b.ns + Math.max(0, n - ctx),
        ol: n > ctx ? b.ol.slice(-ctx) : b.ol,
        nl: n > ctx ? b.nl.slice(-ctx) : b.nl,
        key: `e${keyCounter++}`,
      });
    } else if (i > changeIndices[changeIndices.length - 1]) {
      const keep = Math.min(n, ctx);
      result.push({
        tag: 'equal', os: b.os, ns: b.ns,
        ol: b.ol.slice(0, keep), nl: b.nl.slice(0, keep),
        key: `e${keyCounter++}`,
      });
      if (n > ctx) {
        result.push({
          tag: 'fold', os: b.os + ctx, ns: b.ns + ctx,
          ol: b.ol.slice(ctx), nl: b.nl.slice(ctx),
          count: n - ctx, key: `f${keyCounter++}`,
        });
      }
    } else {
      if (n <= ctx * 2) {
        result.push({ ...b, key: `e${keyCounter++}` });
      } else {
        result.push({
          tag: 'equal', os: b.os, ns: b.ns,
          ol: b.ol.slice(0, ctx), nl: b.nl.slice(0, ctx),
          key: `e${keyCounter++}`,
        });
        const mid = n - ctx * 2;
        result.push({
          tag: 'fold', os: b.os + ctx, ns: b.ns + ctx,
          ol: b.ol.slice(ctx, ctx + mid), nl: b.nl.slice(ctx, ctx + mid),
          count: mid, key: `f${keyCounter++}`,
        });
        result.push({
          tag: 'equal',
          os: b.os + n - ctx, ns: b.ns + n - ctx,
          ol: b.ol.slice(-ctx), nl: b.nl.slice(-ctx),
          key: `e${keyCounter++}`,
        });
      }
    }
  }

  return result;
}

function blockRows(block: DiffBlock): DiffRow[] {
  if (block.tag === 'fold') return [];

  const DEL_BG = 'del-bg';
  const DEL_COLOR = 'del-color';
  const ADD_BG = 'add-bg';
  const ADD_COLOR = 'add-color';
  const EQ_BG = 'eq-bg';
  const EQ_COLOR = 'eq-color';

  if (block.tag === 'equal') {
    return block.ol.map((ol, i) => ({
      oldNum: String(block.os + i + 1),
      oldText: ol,
      oldBgClass: EQ_BG,
      oldColorClass: EQ_COLOR,
      newNum: String(block.ns + i + 1),
      newText: block.nl[i],
      newBgClass: EQ_BG,
      newColorClass: EQ_COLOR,
    }));
  }

  // change block
  const rows: DiffRow[] = [];
  const { ol, nl } = block;
  const maxLen = Math.max(ol.length, nl.length);
  for (let i = 0; i < maxLen; i++) {
    const hasO = i < ol.length;
    const hasN = i < nl.length;
    rows.push({
      oldNum: hasO ? String(block.os + i + 1) : '',
      oldText: hasO ? ol[i] : '',
      oldBgClass: hasO ? DEL_BG : EQ_BG,
      oldColorClass: hasO ? DEL_COLOR : EQ_COLOR,
      newNum: hasN ? String(block.ns + i + 1) : '',
      newText: hasN ? nl[i] : '',
      newBgClass: hasN ? ADD_BG : EQ_BG,
      newColorClass: hasN ? ADD_COLOR : EQ_COLOR,
    });
  }
  return rows;
}

function openFold(key: string) {
  expandedKeys.add(key);
}

function expandAll() {
  for (const b of blocks.value) {
    if (b.tag === 'fold') {
      expandedKeys.add(b.key);
    }
  }
}
</script>

<style scoped>
.diff-viewer {
  border: 1px solid #E2E8F0;
  border-radius: 8px;
  overflow: hidden;
  margin: 8px 0;
  font-family: Consolas, monospace;
}

.diff-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  background: #F8F9FB;
  cursor: pointer;
  user-select: none;
}

.arrow {
  font-size: 12px;
  color: #6366F1;
  flex-shrink: 0;
}

.filename {
  font-size: 16px;
  font-weight: 600;
  color: #1E1B3A;
  white-space: nowrap;
}

.summary {
  font-family: Consolas, monospace;
  font-size: 15px;
  color: #64748B;
  background: #F1F5F9;
  padding: 1px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}

.filepath {
  font-size: 14px;
  color: #94A3B8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.diff-body {
  border-top: 1px solid #E2E8F0;
}

.expand-row {
  display: flex;
  justify-content: flex-end;
  padding: 2px 6px;
}

.expand-all-btn {
  background: none;
  border: none;
  font-family: Consolas, monospace;
  font-size: 14px;
  color: #64748B;
  cursor: pointer;
  padding: 2px 8px;
}

.expand-all-btn:hover {
  color: #334155;
}

.diff-scroll {
  max-height: 500px;
  overflow-y: auto;
}

.fold-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 3px 0;
  background: #F1F5F9;
  font-size: 14px;
  color: #94A3B8;
  cursor: pointer;
  user-select: none;
}

.fold-row:hover {
  background: #E2E8F0;
}

.fold-icon {
  font-size: 14px;
}

.diff-row {
  display: flex;
  min-height: 26px;
}

.diff-side {
  flex: 1;
  display: flex;
  align-items: stretch;
  min-width: 0;
  overflow: hidden;
}

.diff-side.del-bg { background: #FEE2E2; }
.diff-side.add-bg { background: #DCFCE7; }
.diff-side.eq-bg { background: #FFFFFF; }

.line-num {
  width: 44px;
  min-width: 44px;
  text-align: right;
  padding-right: 4px;
  font-family: Consolas, monospace;
  font-size: 13px;
  color: #94A3B8;
  line-height: 26px;
  flex-shrink: 0;
}

.line-spacer {
  width: 8px;
  flex-shrink: 0;
}

.code-text {
  font-family: Consolas, monospace;
  font-size: 14px;
  line-height: 26px;
  white-space: pre;
  overflow: hidden;
  flex: 1;
}

.code-text.del-color { color: #991B1B; }
.code-text.add-color { color: #166534; }
.code-text.eq-color { color: #334155; }

.diff-divider {
  width: 1px;
  background: #E2E8F0;
  flex-shrink: 0;
}
</style>
