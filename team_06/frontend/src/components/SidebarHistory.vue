<script setup>
import clockIcon from '../assets/icons/clock.svg'

const props = defineProps({
  history: { type: Array, default: () => [] },
  agentState: { type: Object, default: null }
})
const emit = defineEmits(['restore'])
</script>

<template>
  <section class="sidebar-section">
    <div class="sidebar-section-title">
      <img :src="clockIcon" alt="Iterations" width="20" height="20" style="opacity:0.6;" />
      Iterations
    </div>
    <template v-if="props.history && props.history.length">
      <ul class="history-list">
        <li
          v-for="(item, i) in [...props.history].reverse()"
          :key="item.layoutId + i"
          class="history-item"
          :class="{ active: props.agentState?.layoutId === item.layoutId }"
          @click="emit('restore', item)"
        >
          <div class="history-item-id">{{ item.layoutId?.length > 10 ? item.layoutId.slice(0, 10) + '…' : item.layoutId }}</div>
          <div class="history-item-desc">{{ item.apartment.attributes?.description || '–' }}</div>
        </li>
      </ul>
    </template>
    <template v-else>
      <p class="sidebar-empty">No iterations yet</p>
    </template>
  </section>
</template>

<style scoped>
.sidebar-section { margin-bottom: 12px; }
.sidebar-section-title {
  display: flex;
  align-items: center;
  font-size: var(--font-size-bold);
  font-weight: 600;
  margin-bottom: 24px;
  color: var(--color-text-secondary);
  gap: 8px;
}
.history-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.history-item {
  padding: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.history-item:hover {
  border-color: var(--color-blue);
  background: var(--color-light-blue);
}
.history-item.active {
  background: var(--color-light-blue);
  border-color: var(--color-blue);
  border-width: 1.5px;
}
.history-item-id {
  font-size: var(--font-size-bold);
  font-weight: 600;
  color: var(--color-text-primary);
}
.history-item-desc {
  font-size: var(--font-size-standard);
  color: var(--color-text-secondary);
  margin-top: 2px;
}
.sidebar-empty {
  font-size: var(--font-size-standard);
  color: var(--color-text-secondary);
  margin: 0;
}
</style>
