<template>
  <Teleport to="body">
    <div class="dialog-overlay" @click.self="$emit('close')">
      <div class="dialog">
        <h3>技能管理 ({{ skills.length }})</h3>

        <div v-if="skills.length" class="skill-list">
          <div v-for="s in skills" :key="s.name" class="skill-card">
            <div class="skill-name">{{ s.name }}</div>
            <div v-if="s.description" class="skill-desc">{{ s.description }}</div>
          </div>
        </div>
        <p v-else class="empty-state">暂无可用技能</p>

        <div class="dialog-actions">
          <button class="btn-cancel" @click="$emit('close')">关闭</button>
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

<style scoped>
.dialog-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; z-index: 100; }
.dialog { background: white; border-radius: 12px; padding: 24px; min-width: 380px; max-width: 500px; box-shadow: 0 4px 24px rgba(0,0,0,0.12); max-height: 80vh; overflow-y: auto; }
.dialog h3 { margin-bottom: 16px; font-size: 17px; color: #1E1B3A; }

.empty-state { color: #94A3B8; font-size: 14px; text-align: center; padding: 24px 0; }

.skill-card { padding: 8px 12px; border: 1px solid #E2E6EC; border-radius: 8px; margin-bottom: 6px; }
.skill-name { font-weight: 600; font-size: 14px; color: #1E1B3A; }
.skill-desc { font-size: 13px; color: #64748B; margin-top: 2px; white-space: pre-wrap; }

.dialog-actions { display: flex; justify-content: flex-end; margin-top: 16px; }
.btn-cancel { padding: 7px 18px; border: 1px solid #E2E6EC; border-radius: 6px; background: white; cursor: pointer; font-size: 14px; }
.btn-cancel:hover { background: #FAFBFC; }
</style>
