<script setup>
import { computed } from 'vue'
import { getDaylightColor, formatDaylight, PROGRAM_COLORS } from '../utils/roomAnalysis.js'

const props = defineProps({
  layout: { type: Object, default: null },
  viewMode: { type: String, default: 'layout' }
})
const issues = []

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
</script>

<template>
  <div class="layout-summary-card">
    <template v-if="props.layout">
      <!-- Title always shown -->
      <div class="layout-summary-title">{{ displayId }}</div>

      <!-- DAYLIGHT MODE -->
      <template v-if="props.viewMode === 'daylight'">
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
  min-width: 180px;
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
</style>