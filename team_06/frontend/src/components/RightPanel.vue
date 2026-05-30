
<script setup>
import userIcon from '../assets/user.svg'
import chevronIcon from '../assets/chevron.svg'
import ToolBar from './ToolBar.vue'
</script>

<template>
  <aside class="right-panel">
    <header class="right-header">
      <div class="right-header-avatar">
        <img :src="userIcon" alt="User" width="32" height="32" style="border-radius:50%;background:#e0e3ea;" />
        <img :src="chevronIcon" alt="Chevron" width="18" height="18" />
      </div>
    </header>
    <div class="toolbar-save-row">
      <div class="toolbar-card toolbar-inline">
        <ToolBar />
      </div>
      <button class="layout-btn save-layout-btn right">Save Layout</button>
    </div>
    <div class="canvas-area">
      <div class="canvas">Canvas Area</div>
    </div>
  </aside>
</template>

<style scoped> 
.right-panel {
  flex: 1 1 0;
  min-width: 0;
  background: var(--color-grey-bg);
  display: flex;
  flex-direction: column;
  align-items: stretch;
  padding: 0 0 0 0;
  border-left: 1px solid var(--color-border);
}
.right-header {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  padding: 28px 32px 0 0;
  gap: 0;
  position: relative;
}
.right-header-avatar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.save-layout-btn.right {
  margin: 0;
  position: static;
  align-self: flex-start;
}
.save-layout-btn {
  margin-left: auto;
  margin-right: auto;
}
.canvas-area {
  flex: 1 1 auto;
  display: flex;
  justify-content: center;
  align-items: center;
  margin: 28px;
}
.canvas {
  background: var(--color-white);
  border-radius: var(--radius-card);
  border: 1px solid var(--color-border);
  width: 100%;
  height: 100%;
  min-height: 0;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
.toolbar-save-row {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: flex-end;
  margin: 16px 32px 0 0;
}
.toolbar-save-group {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}
.toolbar-card {
    margin-left: auto;
  margin-right: auto;
  background: var(--color-white);
  border-radius: var(--radius);
  border: 1px solid var(--color-border);
  padding: 10px 18px;
  justify-content: center;
  align-items: center;
  width: fit-content;
  min-width: 0;
}

@media (max-width: 1200px) {
  .right-panel {
    width: 280px;
  }
  .sidebar {
    width: 180px;
    padding: 24px 10px 16px 10px;
  }
  .canvas-area {
    margin: 16px 10px 0 10px;
  }
}

@media (max-width: 900px) {
  .app-layout {
    flex-direction: column;
  }
  .nav-tab, .sidebar, .right-panel {
    width: 100vw;
    min-width: 0;
    max-width: 100vw;
    flex-direction: row;
    padding: 0;
  }
  .center-panel {
    min-width: 0;
    padding: 0;
  }
}
</style>