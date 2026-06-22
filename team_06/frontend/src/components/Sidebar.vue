<script setup>
import { ref } from 'vue'
import SidebarHeader from './SidebarHeader.vue'
import SidebarBrief from './SidebarBrief.vue'
import SidebarHistory from './SidebarHistory.vue'
import chevronIcon from '../assets/icons/chevron.svg'

const props = defineProps({
  parsedInput: { type: Object, default: null },
  history:     { type: Array,  default: () => [] },
  agentState:  { type: Object, default: null },
  previewId:   { type: String, default: null },
})
const emit = defineEmits(['restore', 'preview', 'clearPreview'])

const historyOpen = ref(false)
</script>

<template>
  <aside class="sidebar">
    <SidebarHeader />
    <div class="sidebar-content">
      <span class="section-title">Brief</span>
      <SidebarBrief :parsedInput="props.parsedInput" />

      <div class="history-section">
        <button class="history-toggle" @click="historyOpen = !historyOpen">
          <span>History</span>
          <img :src="chevronIcon" alt="" width="16" height="16" :class="{ rotated: historyOpen }" />
        </button>
        <div v-if="historyOpen" class="history-body">
          <SidebarHistory :history="props.history" :agentState="props.agentState" :previewId="props.previewId" @preview="emit('preview', $event)" @restore="emit('restore', $event)" @clearPreview="emit('clearPreview')" />
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 310px;
  min-width: 310px;
  background: white;
  display: flex;
  flex-direction: column;
  height: 100vh;
}
.sidebar-content {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 28px 28px 0 28px;
  overflow: hidden;
  gap: 0;
}
.section-title {
  font-size: var(--font-size-subtitle);
  color: var(--color-blue);
  margin-bottom: 14px;
  flex-shrink: 0;
}
.history-section {
  margin-top: 28px;
  border-top: 1px solid var(--color-border);
  flex: 1 1 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.history-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: none;
  border: none;
  padding: 14px 0;
  cursor: pointer;
  font-size: var(--font-size-subtitle);
  color: var(--color-blue);
  transition: opacity 0.15s;
}
.history-toggle:hover {
  opacity: 0.75;
}
.history-toggle img {
  opacity: 0.5;
  transition: transform 0.2s;
}
.history-toggle img.rotated {
  transform: rotate(180deg);
}
.history-body {
  flex: 1 1 0;
  min-height: 0;
  overflow-y: auto;
  padding-bottom: 24px;
}
</style>
