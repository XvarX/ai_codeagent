<template>
  <div class="border border-border-subtle rounded-lg overflow-hidden my-2 font-mono">
    <div class="flex items-center gap-[6px] p-[8px_10px] bg-surface-1 cursor-pointer select-none" @click="open = !open">
      <span class="text-xs text-accent flex-shrink-0">{{ open ? '▼' : '▶' }}</span>
      <span class="text-base font-semibold text-text-primary whitespace-nowrap">{{ filename }}</span>
      <span class="font-mono text-sm text-text-secondary bg-surface-2 px-[6px] py-px rounded-sm flex-shrink-0">+{{ added }} -{{ removed }}</span>
      <span class="text-sm text-text-muted overflow-hidden text-ellipsis whitespace-nowrap flex-1 min-w-0">{{ filePath }}</span>
    </div>
    <div v-if="open" class="border-t border-border-subtle">
      <div class="flex justify-end p-[2px_6px]">
        <button class="bg-transparent border-none font-mono text-sm text-text-secondary cursor-pointer py-0.5 px-2 hover:text-text-primary" @click="expandAll">&#8691; Expand All</button>
      </div>
      <div class="max-h-[500px] overflow-y-auto">
        <template v-for="block in resolvedBlocks" :key="block.key">
          <div
            v-if="block.tag === 'fold'"
            class="flex items-center justify-center gap-1 p-[3px_0] bg-surface-2 text-sm text-text-muted cursor-pointer select-none hover:bg-surface-3"
            @click="openFold(block.key)"
          >
            <span>{{ block.count }} lines unchanged</span>
            <span class="text-sm">&#8691;</span>
          </div>
          <template v-else>
            <div
              v-for="(row, ri) in blockRows(block)"
              :key="block.key + '-' + ri"
              class="flex min-h-[26px]"
            >
              <div class="flex-1 flex items-stretch min-w-0 overflow-hidden" :class="bgClass(row.oldBgClass)">
                <span class="w-[44px] min-w-[44px] text-right pr-1 font-mono text-[13px] text-text-muted leading-[26px] flex-shrink-0">{{ row.oldNum }}</span>
                <span class="w-2 flex-shrink-0"></span>
                <span class="font-mono text-sm leading-[26px] whitespace-pre overflow-hidden flex-1" :class="textClass(row.oldColorClass)">{{ row.oldText }}</span>
              </div>
              <div class="w-px bg-border-subtle flex-shrink-0"></div>
              <div class="flex-1 flex items-stretch min-w-0 overflow-hidden" :class="bgClass(row.newBgClass)">
                <span class="w-[44px] min-w-[44px] text-right pr-1 font-mono text-[13px] text-text-muted leading-[26px] flex-shrink-0">{{ row.newNum }}</span>
                <span class="w-2 flex-shrink-0"></span>
                <span class="font-mono text-sm leading-[26px] whitespace-pre overflow-hidden flex-1" :class="textClass(row.newColorClass)">{{ row.newText }}</span>
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

function bgClass(cls: string) {
  return { 'del-bg': 'bg-danger-subtle', 'add-bg': 'bg-success-subtle', 'eq-bg': 'bg-transparent' }[cls] || 'bg-transparent';
}

function textClass(cls: string) {
  return { 'del-color': 'text-red-700', 'add-color': 'text-green-700', 'eq-color': 'text-text-secondary' }[cls] || 'text-text-secondary';
}
</script>
