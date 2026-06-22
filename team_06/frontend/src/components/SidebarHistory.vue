<script setup>
const props = defineProps({
  history:   { type: Array,  default: () => [] },
  agentState:{ type: Object, default: null },
  previewId: { type: String, default: null },
})
const emit = defineEmits(['preview', 'restore', 'clearPreview'])
</script>

<template>
  <section class="sidebar-section">
    <template v-if="props.history && props.history.length">
      <ul class="history-list">
        <li
          v-for="(item, i) in [...props.history].reverse()"
          :key="item.layoutId + i"
          class="history-item"
          :class="{
            current:  props.agentState?.layoutId === item.layoutId && !props.previewId,
            previewing: props.previewId === item.layoutId,
          }"
          @click="emit('preview', item)"
        >
          <div class="history-item-id">{{ item.layoutId?.length > 18 ? item.layoutId.slice(0, 18) + '…' : item.layoutId }}</div>
          <div class="history-item-desc">{{ item.apartment?.attributes?.description || '–' }}</div>
          <div v-if="props.previewId === item.layoutId" class="history-item-actions">
            <button class="btn-restore" @click.stop="emit('restore', item)">Restore</button>
            <button class="btn-close"   @click.stop="emit('clearPreview')">✕</button>
          </div>
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
.history-item.current {
  background: var(--color-light-blue);
  border-color: var(--color-blue);
  border-width: 1.5px;
}
.history-item.previewing {
  background: #fff8ec;
  border-color: #F5A020;
  border-width: 1.5px;
}
.history-item-actions {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}
.btn-restore {
  flex: 1;
  padding: 4px 8px;
  background: var(--color-blue);
  color: white;
  border: none;
  border-radius: var(--radius);
  font-size: var(--font-size-small);
  font-weight: 600;
  cursor: pointer;
}
.btn-restore:hover { opacity: 0.85; }
.btn-close {
  padding: 4px 8px;
  background: none;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  font-size: var(--font-size-small);
  cursor: pointer;
  color: var(--color-text-secondary);
}
.btn-close:hover { background: var(--color-grey-bg); }
.history-item-id {
  font-size: var(--font-size-bold);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-secondary);
  margin-bottom: 6px;
}
.history-item-desc {
  font-size: var(--font-size-small);
  font-weight: 500;
  color: var(--color-text-primary);
  line-height: 1.4;
}
.sidebar-empty {
  margin: 0 0 0 28px;
  font-size: var(--font-size-small);
  color: var(--color-text-secondary);
  font-style: italic;
}
</style>
