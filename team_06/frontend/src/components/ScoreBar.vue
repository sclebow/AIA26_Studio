<script setup>
import { computed } from 'vue'

const props = defineProps({
  label:     { type: String,  required: true },
  score:     { type: Number,  default: null },   // 0–100 or null
  available: { type: Boolean, default: true },
  threshold: { type: Number,  default: null },   // 0–100 position for tick mark
  passing:   { type: Boolean, default: null },   // explicit pass/fail override; null = auto
  detail:    { type: String,  default: null },   // small secondary text (e.g. raw DA value)
})

const isAvailable = computed(() => props.available && props.score != null)

const fillPct = computed(() =>
  isAvailable.value ? Math.max(0, Math.min(100, props.score)) : 0
)

const isPassing = computed(() => {
  if (props.passing != null) return props.passing
  if (props.threshold == null || !isAvailable.value) return true
  return props.score >= props.threshold
})
</script>

<template>
  <div class="score-bar-row" :class="{ unavailable: !isAvailable }">
    <div class="score-bar-label">{{ label }}</div>
    <div class="score-bar-track">
      <div
        class="score-bar-fill"
        :class="{ failing: isAvailable && !isPassing }"
        :style="{ width: fillPct + '%' }"
      />
      <div
        v-if="threshold != null"
        class="score-bar-tick"
        :style="{ left: threshold + '%' }"
      />
    </div>
    <div class="score-bar-value" :class="{ failing: isAvailable && !isPassing }">
      <template v-if="isAvailable">
        {{ score }}<span class="score-pct">%</span><span v-if="detail" class="score-detail"> · {{ detail }}</span>
      </template>
      <span v-else class="score-na">–</span>
    </div>
  </div>
</template>

<style scoped>
.score-bar-row {
  display: grid;
  grid-template-columns: 1fr auto;
  grid-template-rows: auto auto;
  column-gap: 10px;
  row-gap: 4px;
  align-items: center;
}
.score-bar-label {
  grid-column: 1;
  grid-row: 1;
  font-size: var(--font-size-small);
  color: var(--color-text-secondary);
  white-space: nowrap;
}
.score-bar-value {
  grid-column: 2;
  grid-row: 1;
  font-size: var(--font-size-small);
  font-weight: 600;
  color: var(--color-blue);
  white-space: nowrap;
  text-align: right;
  min-width: 36px;
}
.score-bar-track {
  grid-column: 1 / 3;
  grid-row: 2;
  position: relative;
  height: 5px;
  border-radius: 99px;
  background: var(--color-grey-bg);
  border: 1px solid var(--color-border);
  overflow: visible;
}
.score-bar-fill {
  position: absolute;
  inset: 0 auto 0 0;
  border-radius: 99px;
  background: var(--gradient-btn);
  transition: width 0.4s ease;
}
.score-bar-fill.failing {
  background: #e03131;
}
.score-bar-tick {
  position: absolute;
  top: -3px;
  width: 2px;
  height: 11px;
  border-radius: 1px;
  background: var(--color-text-secondary);
  transform: translateX(-50%);
  opacity: 0.6;
}
.score-pct {
  font-size: 0.7em;
  font-weight: 400;
  margin-left: 1px;
}
.score-detail {
  font-size: 0.75em;
  font-weight: 400;
  color: var(--color-text-secondary);
}
.score-bar-value.failing {
  color: #e03131;
}
.score-na {
  color: var(--color-text-secondary);
  font-weight: 400;
}
/* Dim the whole row when not yet available */
.unavailable .score-bar-label,
.unavailable .score-bar-value {
  color: var(--color-border);
}
</style>
