<script setup>
import { getDaylightColor, formatDaylight } from '../utils/roomAnalysis.js'

const props = defineProps({
  layout: { type: Object, default: null },
  viewMode: { type: String, default: 'layout' }
})
const issues = []
</script>

<template>
  <div class="layout-summary-card">
    <template v-if="props.layout && props.layout.rooms && props.layout.rooms.length">
      <div class="layout-summary-title">{{ (props.layout.layoutId || 'Layout').charAt(0).toUpperCase() + (props.layout.layoutId || 'Layout').slice(1) }}</div>
      <div class="layout-summary-area">
        <template v-if="props.viewMode === 'daylight'">
          {{ (props.layout.rooms.reduce((sum, r) => sum + (r.attributes?.daylight ?? 0), 0) / props.layout.rooms.length).toFixed(2) }}<span style="font-size:1.1rem;font-weight:400;"> avg DA</span>
        </template>
        <template v-else>
          {{ props.layout.rooms.reduce((sum, r) => sum + (r.attributes?.area || 0), 0).toFixed(2) }}<span style="font-size:1.1rem;font-weight:400;"> m²</span>
        </template>
      </div>
      <ul class="layout-summary-list">
        <li v-for="room in props.layout.rooms" :key="room.id" class="layout-summary-room-row">
          <template v-if="props.viewMode === 'daylight'">
            <span class="room-swatch" :style="{ background: getDaylightColor(room.attributes?.daylight ?? 0) }"></span>
            {{ room.name || room.attributes?.program }} - {{ formatDaylight(room.attributes?.daylight) }}
          </template>
          <template v-else>
            {{ room.name || room.attributes?.program }} - {{ room.attributes?.area }} m²
          </template>
        </li>
      </ul>
      <div class="layout-summary-issues" v-if="issues && issues.length">
        <div class="layout-summary-issues-title">Issues</div>
        <ul class="layout-summary-issues-list">
          <li v-for="(issue, idx) in issues" :key="idx">{{ issue }}</li>
        </ul>
      </div>
    </template>
    <template v-else>
      <div class="layout-summary-title">No layout yet</div>
      <div class="layout-summary-area">--</div>
      <ul class="layout-summary-list">
        <li>No input yet</li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.layout-summary-card {
  background: var(--color-white);
  border-radius: var(--radius-card);
  border: 1px solid var(--color-border);
  font-size: var(--font-size-standard);
  color: var(--color-text);
  min-width: 180px;
   padding: 32px 32px;
}
.layout-summary-title {
  font-size: var(--font-size-bold);
  font-weight: var(--font-weight-bold);
  margin-bottom: 18px;
}
.layout-summary-area {
  font-size: var(--font-size-title);
  font-weight: var(--font-weight-bold);
  margin-bottom: 12px;
  color: var(--color-blue);
}
.layout-summary-list {
  margin: 0 0 12px 0;
  padding: 0;
  list-style: none;
  color: var(--color-text-primary);
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
</style>