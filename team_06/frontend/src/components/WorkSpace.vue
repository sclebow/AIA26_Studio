
<script setup>
import userIcon from '../assets/icons/user.svg'
import chevronIcon from '../assets/icons/chevron.svg'
import ToolBar from './ToolBar.vue'
import LayoutCanvas from './LayoutCanvas.vue'
import LayoutCard from './LayoutCard.vue'
import EmbeddingMap from './EmbeddingMap.vue'

import { watch, ref, computed } from 'vue'
const props = defineProps({
  agentState:       { type: Object,  default: null },
  parsedInput:      { type: Object,  default: null },
  isHistoryPreview: { type: Boolean, default: false },
})
const emit = defineEmits(['layoutLoaded', 'selectLayout', 'previewLayout', 'findInBetween', 'restorePreview', 'clearPreview'])
const viewMode = ref('layout')
const activeRooms = ref({})
const activeStep = ref(0)

const hasDaylight = computed(() =>
  (props.agentState?.rooms ?? []).some(r => r.attributes?.daylight != null)
)

const hasEmbeddingMap = computed(() =>
  !!(props.agentState?.embedding_map?.all_coords)
)

const hasRoutine = computed(() => {
  const routine = props.agentState?.routine
  if (!routine || typeof routine !== 'object') return false
  const personas = Array.isArray(routine.personas) ? routine.personas : Array.isArray(routine) ? routine : []
  return personas.length > 0
})

function onViewChange(mode) {
  viewMode.value = mode
}

function exportLayout() {
  if (!props.agentState) return
  const blob = new Blob([JSON.stringify(props.agentState, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${props.agentState.layoutId || 'layout'}.json`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <aside class="work-panel">
    <header class="work-header">
      <button class="default-btn export-btn" :disabled="!props.agentState" @click="exportLayout">Export</button>
    </header>
      <div class="toolbar-card toolbar-inline">
        <ToolBar :viewMode="viewMode" :hasLayout="!!props.agentState" :hasDaylight="hasDaylight" :hasRoutine="hasRoutine" :hasEmbeddingMap="hasEmbeddingMap" @viewChange="onViewChange" @layoutLoaded="emit('layoutLoaded', $event)" />
      </div>
      <div v-if="props.isHistoryPreview" class="preview-banner">
        Previewing history snapshot
        <div class="preview-banner-actions">
          <button class="btn-banner-restore" @click="emit('restorePreview')">Restore</button>
          <button class="btn-banner-close"   @click="emit('clearPreview')">✕ Back</button>
        </div>
      </div>

      <template v-if="props.agentState">
        <div class="canvas-area">
          <div class="canvas-container" :class="{ 'canvas-explore': viewMode === 'explore' }">
            <EmbeddingMap
              v-if="viewMode === 'explore' && hasEmbeddingMap"
              :embeddingMap="props.agentState.embedding_map"
              :searchResults="props.agentState.searchResults ?? []"

              @selectLayout="id => { viewMode = 'layout'; emit('selectLayout', id) }"
              @previewLayout="id => { viewMode = 'layout'; emit('previewLayout', id) }"
              @findInBetween="(a, b) => emit('findInBetween', a, b)"
            />
            <LayoutCanvas
              v-else
              :layout="props.agentState"
              :viewMode="viewMode"
              :activeRooms="activeRooms"
              :activeStep="activeStep"
            />
          </div>
          <LayoutCard
            v-if="viewMode !== 'explore'"
            :layout="props.agentState"
            :viewMode="viewMode"
            :routine="props.agentState?.routine?.personas ?? props.agentState?.routine ?? null"
            @activeRoomsChange="activeRooms = $event"
            @timeStepChange="activeStep = $event"
          />
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
  min-height: 0;
  display: flex;
  justify-content: flex-start;
  align-items: stretch;
  margin: 28px;
  gap: 18px;
}
.canvas-container {
  background: var(--color-white);
  border-radius: var(--radius-card);
  border: 1px solid var(--color-border);
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
.canvas-container.canvas-explore {
  border: none;
  background: var(--color-grey-bg);
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

.preview-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #f0fcfb;
  border-bottom: 1px solid #00B8A8;
  padding: 8px 24px;
  font-size: var(--font-size-small);
  color: #007a70;
  font-weight: 500;
  flex-shrink: 0;
}
.preview-banner-actions {
  display: flex;
  gap: 8px;
}
.btn-banner-restore {
  padding: 4px 12px;
  background: #00B8A8;
  color: white;
  border: none;
  border-radius: var(--radius);
  font-size: var(--font-size-small);
  font-weight: 600;
  cursor: pointer;
}
.btn-banner-restore:hover { opacity: 0.85; }
.btn-banner-close {
  padding: 4px 10px;
  background: none;
  border: 1px solid #00B8A8;
  border-radius: var(--radius);
  font-size: var(--font-size-small);
  color: #007a70;
  cursor: pointer;
}
.btn-banner-close:hover { background: #ccf5f2; }

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