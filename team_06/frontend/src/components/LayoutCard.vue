<script setup>
import { computed, ref, watch } from 'vue'
import { getDaylightColor, formatDaylight, PROGRAM_COLORS, toNumericValue, getRoomDisplayName } from '../utils/roomAnalysis.js'

const ROUTINE_TIMES = [
  '06:00', '07:00', '08:00', '09:00', '10:00', '11:00',
  '12:00', '13:00', '14:00', '15:00', '16:00', '17:00',
  '18:00', '19:00', '20:00', '21:00', '22:00',
]
import ScoreBar from './ScoreBar.vue'

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
    const roomId = stepRoomId(p.steps?.[activeStep.value])
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

const evaluation = computed(() => props.layout?.evaluation ?? null)


// Prefer backend-computed daylight score, fall back to frontend calculation
const daylightScore = computed(() => {
  const backendScore = evaluation.value?.daylight_score
  if (typeof backendScore === 'number') return backendScore

  const rooms = Array.isArray(props.layout?.rooms) ? props.layout.rooms : []
  const scoredRooms = rooms
    .map((room) => {
      const daylight = toNumericValue(room.attributes?.daylight)
      if (daylight == null) return null
      const program = room.attributes?.program
      const target = { living: 2.0, bed: 1.5, walkincloset: 1.2, circulation: 1.0, bath: 0.4, wc: 0.3, storage: 0.5 }[program] ?? 1.0
      return Math.max(0, Math.min(1, daylight / target)) * 100
    })
    .filter((v) => typeof v === 'number')
  return scoredRooms.length ? Math.round(scoredRooms.reduce((a, b) => a + b, 0) / scoredRooms.length) : null
})

// Per-room daylight bars from backend (preferred) or layout rooms
const daylightRooms = computed(() => {
  const backendRooms = evaluation.value?.daylight_rooms
  if (Array.isArray(backendRooms) && backendRooms.length) return backendRooms
  return null
})

const layoutScore = computed(() => {
  const fitScore = evaluation.value?.fit_score
  return typeof fitScore === 'number' ? fitScore : null
})

// Subscores from backend evaluation
const subscores = computed(() => evaluation.value?.subscores ?? null)

// Daylight grouped by area type (frontend grouping from per-room backend data)
const DAYLIGHT_CATEGORIES = [
  { id: 'day_area',   label: 'Day area',   programs: ['living'] },
  { id: 'night_area', label: 'Night area', programs: ['bed', 'walkincloset'] },
  { id: 'wet_rooms',  label: 'Wet rooms',  programs: ['bath', 'wc'] },
]
const daylightCategories = computed(() => {
  const rooms = daylightRooms.value
  if (!rooms?.length) return null
  const result = []
  for (const cat of DAYLIGHT_CATEGORIES) {
    const matching = rooms.filter(r => cat.programs.includes(r.program))
    if (!matching.length) continue
    const score = Math.round(matching.reduce((s, r) => s + r.score, 0) / matching.length)
    result.push({ id: cat.id, label: cat.label, score, available: true, passing: matching.every(r => r.meets_minimum) })
  }
  return result.length ? result : null
})

const displayId = computed(() => {
  const id = props.layout?.layoutId || 'Layout'
  return id.length > 10 ? id.slice(0, 10) + '…' : id
})

function roomNameForId(id) {
  const r = props.layout?.rooms?.find(r => String(r.id) === String(id))
  return r ? (getRoomDisplayName(r) || id) : id
}

// Steps can be null (away) or {room, label} objects from the backend.
function stepRoomId(step) {
  if (!step) return null
  if (typeof step === 'string') return step           // backward compat
  return step.room ?? null
}

function stepActivity(step) {
  if (!step) return 'away'
  if (typeof step === 'string') {
    // backward compat: infer from room program
    const room = props.layout?.rooms?.find(r => String(r.id) === String(step))
    const p = room?.attributes?.program
    return { bed: 'sleeping', bath: 'showering', walkincloset: 'dressing',
             living: 'at home', wc: 'bathroom' }[p] ?? 'at home'
  }
  return step.label || 'at home'
}

const ACTIVITY_ORDER = ['sleeping', 'napping', 'showering', 'dressing', 'working', 'studying',
                        'cooking', 'relaxing', 'playing', 'at home', 'bathroom', 'away']

const activityGroups = computed(() => {
  if (!props.routine) return []
  const groups = {}
  for (const p of props.routine) {
    const step = p.steps?.[activeStep.value]
    const activity = stepActivity(step)
    if (!groups[activity]) groups[activity] = { activity, personas: [] }
    groups[activity].personas.push({ name: p.persona, color: p.color })
  }
  const ordered = ACTIVITY_ORDER.filter(a => groups[a]).map(a => groups[a])
  const rest = Object.values(groups).filter(g => !ACTIVITY_ORDER.includes(g.activity))
  return [...ordered, ...rest]
})

const personaSteps = computed(() => {
  if (!props.routine) return []
  return props.routine.map(p => {
    const step = p.steps?.[activeStep.value]
    const roomId = stepRoomId(step)
    const activity = stepActivity(step)
    const room = roomId ? props.layout?.rooms?.find(r => String(r.id) === String(roomId)) : null
    return {
      name: p.persona,
      color: p.color,
      activity,
      roomName: room?.name ?? null,
      away: step == null,
    }
  })
})

function scoreRingStyle(score) {
  const value = Math.max(0, Math.min(100, score ?? 0))
  const angle = value * 3.6
  return {
    background: `conic-gradient(from 0deg, #00E0CD 0deg, #0067B5 ${angle}deg, #E9ECEF ${angle}deg)`
  }
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
          <div class="persona-step-list">
            <div v-for="p in personaSteps" :key="p.name" class="persona-step-row">
              <span class="persona-step-dot" :style="{ background: p.color }"></span>
              <span class="persona-step-name">{{ p.name }}</span>
              <span class="persona-step-activity" :class="{ away: p.away }">{{ p.activity }}</span>
              <span v-if="!p.away && p.roomName" class="persona-step-room">{{ p.roomName }}</span>
            </div>
          </div>
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
              {{ getRoomDisplayName(room) }} — {{ formatDaylight(room.attributes?.daylight) }}
            </li>
          </ul>

          <div v-if="daylightScore != null" class="evaluation-section">
            <div class="layout-summary-title evaluation-section-title">Daylight quality</div>
            <div class="evaluation-score-ring" :style="scoreRingStyle(daylightScore)">
              <div class="evaluation-score-core">
                <div class="evaluation-score">{{ daylightScore }}</div>
                <div class="evaluation-percent">%</div>
              </div>
            </div>
            <div v-if="daylightCategories" class="subscore-list">
              <ScoreBar
                v-for="cat in daylightCategories"
                :key="cat.id"
                :label="cat.label"
                :score="cat.score"
                :available="cat.available"
              />
            </div>
          </div>
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
        </template>
        <template v-else>
          <div class="layout-summary-area" v-if="props.layout.attributes?.area">
            {{ props.layout.attributes.area.toFixed(2) }}<span style="font-size:1.1rem;font-weight:400;"> m²</span>
          </div>
          <span class="no-rooms-tag">No rooms yet</span>
        </template>

        <ul class="layout-summary-list">
          <li v-for="room in props.layout.rooms" :key="room.id" class="layout-summary-room-row">
            <span class="room-swatch" :style="{ background: PROGRAM_COLORS[room.attributes?.program] ?? '#ddd' }"></span>
            {{ getRoomDisplayName(room) }} — {{ (room.attributes?.area ?? 0).toFixed(1) }} m²
          </li>
        </ul>

        <div v-if="layoutScore != null" class="evaluation-section">
          <div class="layout-summary-title evaluation-section-title">Layout quality</div>
          <div class="evaluation-score-ring" :style="scoreRingStyle(layoutScore)">
            <div class="evaluation-score-core">
              <div class="evaluation-score">{{ layoutScore }}</div>
              <div class="evaluation-percent">%</div>
            </div>
          </div>
          <div v-if="subscores" class="subscore-list">
            <ScoreBar
              v-for="s in subscores"
              :key="s.id"
              :label="s.label"
              :score="s.score"
              :available="s.available"
            />
          </div>
        </div>
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
  width: 280px;
  min-width: 280px;
  max-width: 280px;
  max-height: calc(100vh - 170px);
  overflow-y: auto;
  box-sizing: border-box;
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
.layout-summary-list {
  padding: 0;
  list-style: none;
  margin: 8px 0 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.layout-summary-room-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--font-size-small);
  color: var(--color-text);
}
.room-swatch {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  flex-shrink: 0;
}
.persona-step-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-top: 8px;
}
.persona-step-row {
  display: grid;
  grid-template-columns: 10px 1fr auto auto;
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
  border-radius: 8px;
  background: var(--color-surface, #fff);
  box-shadow: 0 1px 5px rgba(0, 0, 0, 0.08);
}
.persona-step-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.persona-step-name {
  font-size: var(--font-size-small);
  font-weight: var(--font-weight-bold);
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.persona-step-activity {
  font-size: var(--font-size-small);
  color: var(--color-text-secondary);
  white-space: nowrap;
}
.persona-step-activity.away {
  font-style: italic;
  opacity: 0.6;
}
.persona-step-room {
  font-size: var(--font-size-small);
  color: var(--color-text-secondary);
  opacity: 0.55;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 80px;
}
.evaluation-section {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--color-border);
}
.subscore-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 12px 0 4px;
}
.evaluation-score-ring {
  width: 88px;
  height: 88px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 12px;
}
.evaluation-score-core {
  width: 76px;
  height: 76px;
  border-radius: 50%;
  background: white;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.evaluation-score {
  font-size: 1.4rem;
  font-weight: 700;
  color: var(--color-blue);
  line-height: 1;
}
.evaluation-percent {
  font-size: 0.85rem;
  color: var(--color-blue);
  line-height: 1;
}
</style>