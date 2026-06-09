<template>
  <Teleport to="body">
    <div class="fixed inset-0 bg-black/50 flex items-center justify-center z-[100]" @click.self="$emit('close')">
      <div class="bg-surface-1 rounded-xl p-6 min-w-[380px] max-w-[500px] max-h-[80vh] overflow-y-auto shadow-dialog">
        <h3 class="mb-4 text-[17px] font-semibold text-text-primary">技能管理 ({{ skills.length }})</h3>

        <div v-if="skills.length" class="space-y-[6px]">
          <div v-for="s in skills" :key="s.name" class="p-[8px_12px] border border-border-default rounded-lg">
            <div class="font-semibold text-sm text-text-primary">{{ s.name }}</div>
            <div v-if="s.description" class="text-[13px] text-text-secondary mt-0.5 whitespace-pre-wrap">{{ s.description }}</div>
          </div>
        </div>
        <p v-else class="text-text-muted text-sm text-center py-6">暂无可用技能</p>

        <div class="flex justify-end mt-4">
          <button class="px-[18px] py-[7px] border border-border-default rounded-md bg-transparent cursor-pointer text-sm text-text-primary hover:bg-surface-2" @click="$emit('close')">关闭</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useAgentStore } from '../stores/agent';

defineEmits<{ close: [] }>();

const agentStore = useAgentStore();

interface SkillCard {
  name: string;
  description: string;
}

const skills = computed<SkillCard[]>(() => {
  const text = agentStore.skills || '';
  if (!text.trim()) return [];
  return text.split('\n\n').filter(b => b.trim()).map(block => {
    const lines = block.trim().split('\n');
    const colonIdx = lines[0].indexOf(':');
    if (colonIdx > 0) {
      return {
        name: lines[0].slice(0, colonIdx).trim(),
        description: lines[0].slice(colonIdx + 1).trim() + (lines.length > 1 ? '\n' + lines.slice(1).join('\n') : ''),
      };
    }
    return { name: lines[0], description: lines.slice(1).join('\n') };
  });
});
</script>
