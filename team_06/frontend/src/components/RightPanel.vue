
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
      <button class="save-layout-btn right">Save Layout</button>
    </div>
    <div class="canvas-area">
      <div class="canvas">Canvas Area</div>
    </div>
    <div class="layout-summary-card">
      <div class="layout-summary-title">Layout-001</div>
      <div class="layout-summary-area">52<span style="font-size:1.1rem;font-weight:400;">sqm</span></div>
      <ul class="layout-summary-list">
        <li>Bedroom - 16 sqm</li>
        <li>Bathroom - 5 sqm</li>
        <li>Foyer - 2 sqm</li>
        <li>Living - 20 sqm</li>
        <li>Kitchen - 9 sqm</li>
      </ul>
      <div class="layout-summary-issues">
        <div class="layout-summary-issues-title">Issues</div>
        <ul class="layout-summary-issues-list">
          <li>Lack of daylight</li>
          <li>Outline too small</li>
        </ul>
      </div>
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
  padding: 28px 32px 0 32px;
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
  width: 140px;
  min-width: 120px;
  height: 38px;
  font-size: 1rem;
  position: static;
  align-self: flex-start;
}

.save-layout-btn {
  margin: 18px 32px 0 32px;
  background: var(--gradient-btn);
  color: var(--color-white);
  font-weight: 600;
  font-size: var(--font-size-standard);
  border: none;
  border-radius: var(--radius);
  width: 180px;
  height: 44px;
  min-width: 180px;
  min-height: 44px;
  padding: 0;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(33, 118, 255, 0.10);
  transition: box-shadow 0.2s;
  display: block;
  margin-left: auto;
  margin-right: auto;
}
.save-layout-btn:hover {
  box-shadow: 0 4px 16px rgba(33, 118, 255, 0.18);
}
.toolbar {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 18px;
  margin: 0;
}

.chat-input-btn {
  background: none !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 6px;
  display: flex;
  align-items: center;
  color: var(--color-blue);
  font-size: 1.2rem;
  cursor: pointer;
  transition: background 0.15s;
}
.chat-input-btn:focus {
  outline: none;
}
.chat-input-btn:hover {
  background: none;
  box-shadow: none;
}

.canvas-area {
  flex: 1 1 auto;
  display: flex;
  justify-content: center;
  align-items: center;
  margin: 24px 32px 0 32px;
}

.canvas {
  background: var(--color-white);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
  width: 100%;
  max-width: 420px;
  min-height: 320px;
  height: 340px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.layout-summary-card {
  background: var(--color-white);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
  margin: 32px;
  padding: 24px 22px;
  font-size: var(--font-size-standard);
  color: var(--color-text);
  min-width: 180px;
}

.layout-summary-title {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--color-blue);
  margin-bottom: 8px;
}

.layout-summary-area {
  font-size: 2.1rem;
  font-weight: 700;
  margin-bottom: 12px;
}

.layout-summary-list {
  margin: 0 0 12px 0;
  padding: 0;
  list-style: none;
  color: var(--color-text-secondary);
}

.layout-summary-issues {
  margin-top: 10px;
}

.layout-summary-issues-title {
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 4px;
}

.layout-summary-issues-list {
  margin: 0;
  padding: 0 0 0 16px;
  color: var(--color-text-secondary);
  font-size: 0.97rem;
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
  .layout-summary-card {
    margin: 16px;
    padding: 16px 10px;
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