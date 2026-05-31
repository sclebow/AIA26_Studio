<script setup>
import layoutData from '../assets/dummy/layouts.json'

const props = defineProps({
  // ...other props,
  index: {
    type: Number,
    default: 0
  }
})

const layout = layoutData[props.index] || {}
const layoutId = layout.layoutId || 'Layout'
const rooms = layout.rooms || []
const totalArea = rooms.reduce((sum, r) => sum + (r.attributes?.area || 0), 0).toFixed(2)
// Example: you can add logic to compute issues if needed
const issues = []
</script>

<template>
  <div class="layout-summary-card">
    <div class="layout-summary-title">{{ layoutId.charAt(0).toUpperCase() + layoutId.slice(1) }}</div>
    <div class="layout-summary-area">
      {{ totalArea }}<span style="font-size:1.1rem;font-weight:400;"> m²</span>
    </div>
    <ul class="layout-summary-list">
      <li v-for="room in rooms" :key="room.id">
        {{ room.name }} - {{ room.attributes.area }} m²
      </li>
    </ul>
    <div class="layout-summary-issues" v-if="issues && issues.length">
      <div class="layout-summary-issues-title">Issues</div>
      <ul class="layout-summary-issues-list">
        <li v-for="(issue, idx) in issues" :key="idx">{{ issue }}</li>
      </ul>
    </div>
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