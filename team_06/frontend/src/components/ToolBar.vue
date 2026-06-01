<template>
  <div class="toolbar">
    <div class="toolbar-group">
      <button class="layout-input-btn"><img :src="uploadIcon" alt="Upload" width="22" height="22" /></button>
    </div>
    <div class="toolbar-divider"></div>
    <div class="toolbar-group">
      <button class="layout-input-btn view-btn" :class="{ active: viewMode === 'layout' }" @click="emit('viewChange', 'layout')">
        <img :src="viewMode === 'layout' ? layoutBlueIcon : layoutIcon" alt="Layout" width="22" height="22" />
      </button>
      <button class="layout-input-btn view-btn" :class="{ active: viewMode === 'daylight' }" @click="emit('viewChange', 'daylight')">
        <img :src="viewMode === 'daylight' ? sunBlueIcon : sunIcon" alt="Daylight" width="22" height="22" />
      </button>
    </div>
  </div>
</template>

<script setup>
import uploadIcon from '../assets/icons/upload.svg'
import layoutIcon from '../assets/icons/layout.svg'
import layoutBlueIcon from '../assets/icons/layout-blue.svg'
import sunIcon from '../assets/icons/sun.svg'
import sunBlueIcon from '../assets/icons/sun-blue.svg'

defineProps({ viewMode: { type: String, default: 'layout' } })
const emit = defineEmits(['viewChange'])
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 12px;
  margin: 0;
}
.toolbar-group {
  display: flex;
  align-items: center;
  gap: 4px;
}
.toolbar-divider {
  width: 1px;
  height: 20px;
  background: var(--color-border);
  margin: 0 4px;
}
.layout-input-btn {
  background: none !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 6px;
  display: flex;
  align-items: center;
  cursor: pointer;
  opacity: 0.4;
  transition: opacity 0.15s;
}
.layout-input-btn:focus { outline: none; }
.layout-input-btn:hover { opacity: 0.75; }
.layout-input-btn.active { opacity: 1; }
</style>
