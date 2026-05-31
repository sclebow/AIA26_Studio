
<script setup>
import userIcon from '../assets/user.svg'
import chevronIcon from '../assets/chevron.svg'
import ToolBar from './ToolBar.vue'
</script>

<template>
  <aside class="work-panel">
    <header class="work-header">
      <button class="layout-btn save-layout-btn ">Save Layout</button>
    </header>
      <div class="toolbar-card toolbar-inline">
        <ToolBar />
      </div>
    <div class="canvas-area">
      <div class="canvas">Canvas Area</div>
    </div>
  </aside>
</template>

<style scoped> 
.work-panel {
  flex: 1 1 0;
  min-width: 0;
  background: var(--color-grey-bg);
  display: flex;
  flex-direction: column;
  align-items: stretch;
  padding: 0 0 0 0;
  border-left: 1px solid var(--color-border);
  border-right-width: 1px solid var(--color-border);
}
.work-header {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0;
  position: relative;
}
.work-header-avatar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.save-layout-btn {
  margin-right: 24px;
  margin-top: 28px;
  margin-bottom: 12px;
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