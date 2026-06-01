<script setup>
import { computed, ref, watch } from 'vue'
import { getDaylightColor, formatDaylight, PROGRAM_COLORS } from '../utils/roomAnalysis.js'
import { ROUTINE_TIMES } from '../mock/agentMock.js'

const props = defineProps({
  layout:      { type: Object, default: null },
  viewMode:    { type: String, default: 'layout' },
  routine:     { type: Array,  default: null },   // parsedInput.routine
})

const emit = defineEmits(['activeRoomsChange', 'timeStepChange'])

const issues = []

const activeStep = ref(0)

// Reset slider when routine changes or viewMode switches to routine
watch(() => [props.routine, props.viewMode], () => { activeStep.value = 0 })

// { roomId: [{ color, name }, ...] } for the current step
const activeRooms = computed(() => {
  if (props.viewMode !== 'routine' || !props.routine) return {}
  const map = {}
  for (const p of props.routine) {
    const roomId = p.steps?.[activeStep.value]
    if (roomId != null) {
      if (!map[roomId]) map[roomId] = []
      map[roomId].push({ color: p.color, name: p.persona })
    }
  }
  return map
})

// Emit whenever activeRooms changes so WorkSpace can pass it to LayoutCanvas
watch(activeRooms, (val) => emit('activeRoomsChange', val), { immediate: true })
// Emit step index so WorkSpace can pass it to LayoutCanvas for time-of-day colour
watch(activeStep, (val) => emit('timeStepChange', val), { immediate: true })

const hasDaylight = computed(() =>
  (props.layout?.rooms ?? []).some(r => r.attributes?.daylight != null)
)

const hasRooms = computed(() =>
  (props.layout?.rooms ?? []).length > 0
)

const displayId = computed(() => {
  const id = props.layout?.layoutId || 'Layout'
  return id.length > 10 ? id.slice(0, 10) + '…' : id
})

function roomNameForId(id) {
  const r = props.layout?.rooms?.find(r => String(r.id) === String(id))
  return r ? (r.name || r.attributes?.program || id) : id
}
</script>

<template>
  <div class="layout-summary-card">
    <template v-if="props.layout">
      <!-- Title always shown -->
      <div class="layout-summary-title">{{ displayId }}</div>

      <!-- ROUTINE MODE -->
      <template v-if="props.viewMode === 'routine'">
        <template v-if="routine">
          <div class="routine-time-label">{{ ROUTINE_TIMES[activeStep] }}</div>
          <input
            class="routine-slider"
            type="range"
            min="0"
            :max="ROUTINE_TIMES.length - 1"
            step="1"
            v-model.number="activeStep"
          />
          <ul class="layout-summary-list routine-persona-list">
            <li v-for="p in routine" :key="p.persona" class="layout-summary-room-row">
              <span class="room-swatch" :style="{ background: p.color }"></span>
              <span class="routine-persona-name">{{ p.persona }}</span>
              <span class="routine-persona-room">{{ roomNameForId(p.steps?.[activeStep]) ?? '–' }}</span>
            </li>
          </ul>
        </template>
        <template v-else>
          <span class="no-rooms-tag">No routine yet</span>
        </template>
      </template>

      <!-- DAYLIGHT MODE -->
      <template v-else-if="props.viewMode === 'daylight'">
        <template v-if="hasDaylight">
          <div class="layout-summary-area">
            {{ (props.layout.rooms.reduce((sum, r) => sum + (r.attributes?.daylight ?? 0), 0) / props.layout.rooms.length).toFixed(2) }}<span style="font-size:1.1rem;font-weight:400;"> avg DA</span>
          </div>
          <ul class="layout-summary-list">
            <li v-for="room in props.layout.rooms" :key="room.id" class="layout-summary-room-row">
              <span class="room-swatch" :style="{ background: getDaylightColor(room.attributes?.daylight ?? 0) }"></span>
              {{ room.name || room.attributes?.program }} — {{ formatDaylight(room.attributes?.daylight) }}
            </li>
          </ul>
        </template>
        <template v-else>
          <span class="no-rooms-tag">No daylight yet</span>
        </template>
      </template>

      <!-- LAYOUT MODE -->
      <template v-else>
        <template v-if="hasRooms">
          <div class="layout-summary-area">
            {{ props.layout.rooms.reduce((sum, r) => sum + (r.attributes?.area || 0), 0).toFixed(2) }}<span style="font-size:1.1rem;font-weight:400;"> m²</span>
          </div>
          <ul class="layout-summary-list">
            <li v-for="room in props.layout.rooms" :key="room.id" class="layout-summary-room-row">
              <span class="room-swatch" :style="{ background: PROGRAM_COLORS[room.attributes?.program] ?? '#ddd' }"></span>
              {{ room.name || room.attributes?.program }} - {{ (room.attributes?.area ?? 0).toFixed(2) }} m²
            </li>
          </ul>
        </template>
        <template v-else>
          <div class="layout-summary-area" v-if="props.layout.attributes?.area">
            {{ props.layout.attributes.area.toFixed(2) }}<span style="font-size:1.1rem;font-weight:400;"> m²</span>
          </div>
          <span class="no-rooms-tag">No rooms yet</span>
        </template>
      </template>

      <div class="layout-summary-issues" v-if="issues && issues.length">
        <div class="layout-summary-issues-title">Issues</div>
        <ul class="layout-summary-issues-list">
          <li v-for="(issue, idx) in issues" :key="idx">{{ issue }}</li>
        </ul>
      </div>
    </template>
    <!-- No layout -->
    <template v-else>
      <div class="layout-summary-title">No layout yet</div>
      <div class="layout-summary-area">--</div>
    </template>
  </div>
</template>

<style scoped>
.layout-summary-card {
  background: var(--color-white);
  border-radius: var(--radius-card);
  border: 1px solid var(--color-border);
  font-size: var(--font-size-standard);
  min-width: 200px;
   padding: 32px 32px;
}
.layout-summary-title {
  font-size: var(--font-size-bold);
  font-weight: var(--font-weight-bold);
  margin-bottom: 18px;
  color: var(--color-text-secondary);
}
.layout-summary-area {
  font-size: var(--font-size-title);
  font-weight: var(--font-weight-bold);
  color: var(--color-blue);
}
.layout-summary-list {
  padding: 0;
  list-style: none;
  color: var(--color-text-primary);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.layout-summary-room-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.room-swatch {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  flex-shrink: 0;
}
.layout-summary-issues {
  margin-top: 10px;
}
.layout-summary-issues-title {
  font-weight: 600;
  color: var(--color-text-error);
  margin-bottom: 4px;
}
.layout-summary-issues-list {
  margin: 0;
  padding: 0 0 0 16px;
  color: var(--color-text-error);
  font-size: var(--font-size-bold);
}
.no-rooms-tag {
  display: inline-block;
  margin-top: 4px;
  padding: 3px 10px;
  border-radius: 20px;
  border: 1px solid var(--color-border);
  font-size: var(--font-size-standard);
  color: var(--color-text-secondary);
  font-style: italic;
}
.routine-time-label {
  font-size: var(--font-size-title);
  font-weight: var(--font-weight-bold);
  color: var(--color-blue);
  margin-bottom: 8px;
}
.routine-slider {
  width: 100%;
  accent-color: var(--color-blue);
  margin-bottom: 4px;
  cursor: pointer;
}
.routine-ticks {
  display: flex;
  justify-content: space-between;
  margin-bottom: 16px;
}
.routine-tick {
  font-size: 10px;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: color 0.15s;
}
.routine-tick.active {
  color: var(--color-blue);
  font-weight: 600;
}
.routine-persona-list {
  margin-top: 4px;
}
.routine-persona-name {
  flex: 1;
  color: var(--color-text-secondary);
}
.routine-persona-room {
  color: var(--color-text-primary);
  font-weight: 500;
  font-size: var(--font-size-standard);
}
</style>