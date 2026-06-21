<template>
  <div class="toolbar">
    <div class="toolbar-group">
      <div class="tooltip-wrap">
        <button class="layout-input-btn" :class="{ active: !!fileName }" @click="fileInput.click()">
          <img :src="!!fileName ? uploadBlueIcon : uploadIcon" alt="Upload" width="22" height="22" />
        </button>
        <span class="tooltip">{{ fileName ? 'Replace boundary' : 'Upload' }}</span>
      </div>
      <template v-if="fileName">
        <span class="file-name">{{ fileName }}</span>
        <button class="file-clear" @click.stop="clearFile">&times;</button>
      </template>
      <input ref="fileInput" type="file" accept=".json" style="display:none" @change="onFileChange" />
    </div>
    <div class="toolbar-divider"></div>
    <div class="toolbar-group">
      <div class="tooltip-wrap">
        <button class="layout-input-btn view-btn" :class="{ active: hasLayout && viewMode === 'layout' }" :disabled="!hasLayout" @click="hasLayout && emit('viewChange', 'layout')">
          <img :src="hasLayout && viewMode === 'layout' ? layoutBlueIcon : layoutIcon" alt="Layout" width="22" height="22" />
        </button>
        <span class="tooltip">Layout</span>
      </div>
      <div class="tooltip-wrap">
        <button class="layout-input-btn view-btn" :class="{ active: hasDaylight && viewMode === 'daylight' }" :disabled="!hasDaylight" @click="hasDaylight && emit('viewChange', 'daylight')">
          <img :src="hasDaylight && viewMode === 'daylight' ? sunBlueIcon : sunIcon" alt="Daylight" width="22" height="22" />
        </button>
        <span class="tooltip">Daylight</span>
      </div>
      <div class="tooltip-wrap">
        <button class="layout-input-btn view-btn" :class="{ active: hasRoutine && viewMode === 'routine' }" :disabled="!hasRoutine" @click="hasRoutine && emit('viewChange', 'routine')">
          <img :src="hasRoutine && viewMode === 'routine' ? clockBlueIcon : clockIcon" alt="Routine" width="22" height="22" />
        </button>
        <span class="tooltip">Routine</span>
      </div>
      <div class="tooltip-wrap">
        <button class="layout-input-btn view-btn" :class="{ active: hasEmbeddingMap && viewMode === 'explore' }" :disabled="!hasEmbeddingMap" @click="hasEmbeddingMap && emit('viewChange', 'explore')">
          <img :src="hasEmbeddingMap && viewMode === 'explore' ? exploreBlueIcon : exploreIcon" alt="Explore" width="22" height="22" />
        </button>
        <span class="tooltip">Explore</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import uploadIcon from '../assets/icons/upload.svg'
import uploadBlueIcon from '../assets/icons/upload-blue.svg'
import layoutIcon from '../assets/icons/layout.svg'
import layoutBlueIcon from '../assets/icons/layout-blue.svg'
import sunIcon from '../assets/icons/sun.svg'
import sunBlueIcon from '../assets/icons/sun-blue.svg'
import clockIcon from '../assets/icons/clock.svg'
import clockBlueIcon from '../assets/icons/clock-blue.svg'
import exploreIcon from '../assets/icons/explore.svg'
import exploreBlueIcon from '../assets/icons/explore-blue.svg'

defineProps({
  viewMode: { type: String, default: null },
  hasLayout: { type: Boolean, default: false },
  hasDaylight: { type: Boolean, default: false },
  hasRoutine: { type: Boolean, default: false },
  hasEmbeddingMap: { type: Boolean, default: false },
})
const emit = defineEmits(['viewChange', 'layoutLoaded'])

const fileInput = ref(null)
const fileName = ref(null)

function onFileChange(e) {
  const file = e.target.files[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = (ev) => {
    try {
      const json = JSON.parse(ev.target.result)
      fileName.value = file.name
      emit('layoutLoaded', json)
    } catch {
      alert('Invalid JSON file')
    }
  }
  reader.readAsText(file)
  e.target.value = ''
}

function clearFile() {
  fileName.value = null
  emit('layoutLoaded', null)
}
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
.file-name {
  font-size: var(--font-size-standard);
  color: var(--color-text-secondary);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-clear {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 1rem;
  line-height: 1;
  padding: 0 2px;
  color: var(--color-text-secondary);
  opacity: 0.6;
}
.file-clear:hover { opacity: 1; }

.tooltip-wrap {
  position: relative;
  display: flex;
  align-items: center;
}
.tooltip {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 50%;
  transform: translateX(-50%);
  background: var(--color-text, #222);
  color: #fff;
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 4px;
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.15s;
  z-index: 100;
}
.tooltip::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 4px solid transparent;
  border-top-color: var(--color-text, #222);
}
.tooltip-wrap:hover .tooltip { opacity: 1; }
</style>
