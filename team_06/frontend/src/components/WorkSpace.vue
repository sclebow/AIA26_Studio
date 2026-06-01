
<script setup>
import userIcon from '../assets/icons/user.svg'
import chevronIcon from '../assets/icons/chevron.svg'
import ToolBar from './ToolBar.vue'
import LayoutCanvas from './LayoutCanvas.vue'
import LayoutCard from './LayoutCard.vue'

import { watch, ref } from 'vue'
const props = defineProps({
  agentState: {
    type: Object,
    default: null
  }
})
const viewMode = ref('layout')
watch(() => props.agentState, (val) => {
  console.log('WorkSpace agentState changed:', val)
})
console.log('WorkSpace received agentState:', props.agentState);
console.log('WorkSpace agentState:', props.agentState);
</script>

<template>
  <aside class="work-panel">
    <header class="work-header">
      <button class="default-btn export-btn ">Export</button>
    </header>
      <template v-if="props.agentState">
        <div class="toolbar-card toolbar-inline">
          <ToolBar :viewMode="viewMode" @viewChange="viewMode = $event" />
        </div>
        <div class="canvas-area">
          <div class="canvas-container">
            <LayoutCanvas :layout="props.agentState" />
          </div>
          <LayoutCard :layout="props.agentState" />
        </div>
      </template>
      <div v-else class="welcome-screen">
        <h1 class="welcome-title">Welcome to inHabit</h1>
        <p class="welcome-subtitle">AI-powered floor plan generation based on your lifestyle</p>
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
.export-btn {
  margin-right: 24px;
  margin-top: 28px;
  margin-bottom: 12px;
}
.canvas-area {
  flex: 1 1 auto;
  display: flex;
  justify-content: flex-start;
  align-items: flex-start;
  margin: 28px;
  gap: 18px;
}
.canvas-container {
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

.welcome-screen {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px;
  text-align: center;
}
.welcome-title {
  font-size: var(--font-size-title);
  font-weight: 700;
  color: var(--color-blue);
  margin: 0;
}
.welcome-subtitle {
  font-size: var(--font-size-subtitle);
  color: var(--color-text-secondary);
  margin: 0;
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