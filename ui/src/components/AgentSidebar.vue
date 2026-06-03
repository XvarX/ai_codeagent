<template>
  <div class="agent-sidebar">
    <div class="sidebar-header"><h3>Agents</h3></div>
    <div class="agent-list">
      <div class="agent-item active">
        <span class="agent-name">Master</span>
        <span class="agent-status running"></span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.agent-sidebar { width: 180px; border-right: 1px solid #F1F3F6; background: #FAFBFC; padding: 12px; }
.sidebar-header h3 { font-size: 15px; color: #1E1B3A; margin-bottom: 8px; }
.agent-item { display: flex; justify-content: space-between; padding: 6px 8px; border-radius: 6px; cursor: pointer; }
.agent-item:hover { background: #F1F3F6; }
.agent-item.active { background: #EBF5FF; }
.agent-name { font-size: 14px; }
.agent-status { width: 8px; height: 8px; border-radius: 4px; }
.agent-status.running { background: #22C55E; }
</style>
