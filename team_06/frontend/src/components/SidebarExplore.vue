<script setup>
import searchIcon from '../assets/icons/search.svg'

const props = defineProps({
  results: { type: Array, default: () => [] },
  agentState: { type: Object, default: null }
})

const emit = defineEmits(['selectCandidate'])

function formatScore(score) {
  if (typeof score !== 'number' || Number.isNaN(score)) return null
  return `${Math.max(0, Math.min(100, Math.round(score)))}%`
}
</script>

<template>
  <section class="sidebar-section">
    <div class="sidebar-section-title">
      <img :src="searchIcon" alt="Explore" width="20" height="20" style="opacity:0.6;" />
      Explore
    </div>
    <template v-if="props.results && props.results.length">
      <ul class="history-list">
        <li
          v-for="(item, i) in props.results"
          :key="item.layoutId + i"
          class="history-item"
          :class="{ active: props.agentState?.layoutId === item.layoutId }"
          @click="emit('selectCandidate', item)"
        >
          <div class="history-item-top">
            <div class="history-item-id">{{ item.layoutId?.length > 18 ? item.layoutId.slice(0, 18) + '…' : item.layoutId }}</div>
            <div v-if="formatScore(item.score)" class="history-item-score">{{ formatScore(item.score) }}</div>
          </div>
          <div class="history-item-desc">{{ item.layout?.apartment?.attributes?.description || item.name || '–' }}</div>
        </li>
      </ul>
    </template>
    <template v-else>
      <p class="sidebar-empty">No candidates yet</p>
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
  margin-bottom: 20px;
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
.history-item-top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.history-item-id {
  font-size: var(--font-size-bold);
  font-weight: 600;
  color: var(--color-text-primary);
}
.history-item-score {
  font-size: var(--font-size-standard);
  font-weight: 600;
  color: var(--color-blue);
  flex-shrink: 0;
}
.history-item-desc {
  font-size: var(--font-size-standard);
  color: var(--color-text-secondary);
  margin-top: 2px;
}
.sidebar-empty {
  margin: 0 0 0 28px;
  font-size: var(--font-size-small);
  color: var(--color-text-secondary);
  font-style: italic;
}
</style>
