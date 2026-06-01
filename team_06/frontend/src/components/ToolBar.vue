<template>
  <div class="toolbar">
    <div class="toolbar-group">
      <button class="layout-input-btn" :class="{ active: !!fileName }" @click="fileInput.click()" :title="fileName ? 'Replace boundary JSON' : 'Upload boundary JSON'">
        <img :src="!!fileName ? uploadBlueIcon : uploadIcon" alt="Upload" width="22" height="22" />
      </button>
      <template v-if="fileName">
        <span class="file-name">{{ fileName }}</span>
        <button class="file-clear" @click.stop="clearFile" title="Remove file">&times;</button>
      </template>
      <input ref="fileInput" type="file" accept=".json" style="display:none" @change="onFileChange" />
    </div>
    <div class="toolbar-divider"></div>
    <div class="toolbar-group">
      <button class="layout-input-btn view-btn" :class="{ active: hasLayout && viewMode === 'layout' }" :disabled="!hasLayout" @click="hasLayout && emit('viewChange', 'layout')">
        <img :src="hasLayout && viewMode === 'layout' ? layoutBlueIcon : layoutIcon" alt="Layout" width="22" height="22" />
      </button>
      <button class="layout-input-btn view-btn" :class="{ active: hasDaylight && viewMode === 'daylight' }" :disabled="!hasDaylight" @click="hasDaylight && emit('viewChange', 'daylight')">
        <img :src="hasDaylight && viewMode === 'daylight' ? sunBlueIcon : sunIcon" alt="Daylight" width="22" height="22" />
      </button>
      <button class="layout-input-btn view-btn" :class="{ active: hasRoutine && viewMode === 'routine' }" :disabled="!hasRoutine" @click="hasRoutine && emit('viewChange', 'routine')" title="Routine visualization">
        <img :src="hasRoutine && viewMode === 'routine' ? clockBlueIcon : clockIcon" alt="Routine" width="22" height="22" />
      </button>
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

defineProps({
  viewMode: { type: String, default: null },
  hasLayout: { type: Boolean, default: false },
  hasDaylight: { type: Boolean, default: false },
  hasRoutine: { type: Boolean, default: false }
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
</style>
