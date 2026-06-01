<script setup>
import userIcon from '../assets/icons/user.svg'
import clockIcon from '../assets/icons/clock.svg'
import boxIcon from '../assets/icons/box.svg'
import messageIcon from '../assets/icons/message.svg'

const props = defineProps({
  parsedInput: { type: Object, default: null }
})
</script>

<template>
  <section class="sidebar-section">
    <div class="sidebar-section-title">
      <img :src="userIcon" alt="Households" width="20" height="20" style="opacity:0.6;" />
      Households
    </div>
    <ul class="sidebar-list">
      <template v-if="props.parsedInput?.households?.length">
        <li v-for="(h, i) in props.parsedInput.households" :key="i">
          {{ h.name }}<span v-if="h.age && h.age !== 'int'"> - {{ h.age }}</span><span v-if="h.relationship"> - {{ h.relationship }}</span>
        </li>
      </template>
      <li v-else>No input yet</li>
    </ul>
  </section>

  <section class="sidebar-section">
    <div class="sidebar-section-title">
      <img :src="clockIcon" alt="Routine" width="20" height="20" style="opacity:0.6;" />
      Routine
    </div>
    <ul class="sidebar-list">
      <template v-if="props.parsedInput?.activities?.length">
        <li v-for="(a, i) in props.parsedInput.activities" :key="i">
          {{ a.type }}<span v-if="a.time && a.time !== 'int'"> - {{ a.time }}</span>
        </li>
      </template>
      <li v-else>No input yet</li>
    </ul>
  </section>

  <section class="sidebar-section">
    <div class="sidebar-section-title">
      <img :src="boxIcon" alt="Rooms" width="20" height="20" style="opacity:0.6;" />
      Rooms
    </div>
    <ul class="sidebar-list">
      <template v-if="props.parsedInput?.rooms?.length">
        <li v-for="(r, i) in props.parsedInput.rooms" :key="i">
          {{ r.name || r.attributes?.program || 'Room ' + r.id }}<span v-if="r.size"> - {{ r.size }}</span>
        </li>
      </template>
      <li v-else>No input yet</li>
    </ul>
  </section>

  <section class="sidebar-section">
    <div class="sidebar-section-title">
      <img :src="messageIcon" alt="Extra" width="20" height="20" style="opacity:0.6;" />
      Extra
    </div>
    <ul class="sidebar-list">
      <template v-if="props.parsedInput?.extras?.length">
        <li v-for="(e, i) in props.parsedInput.extras" :key="i">{{ e }}</li>
      </template>
      <li v-else>No input yet</li>
    </ul>
  </section>
</template>

<style scoped>
.sidebar-section {
  margin-bottom: 12px;
}
.sidebar-section-title {
  display: flex;
  align-items: center;
  font-size: var(--font-size-bold);
  font-weight: 600;
  margin-bottom: 18px;
  color: var(--color-text-secondary);
  gap: 8px;
}
.sidebar-title-add {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  margin-left: auto;
  display: flex;
  align-items: center;
  opacity: 0.5;
}
.sidebar-title-add:hover { opacity: 1; }
.sidebar-list {
  margin: 0 0 0 28px;
  padding: 0;
  list-style: none;
  font-size: var(--font-size-standard);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.sidebar-list-input-row { list-style: none; }
.sidebar-list-input {
  width: 100%;
  border: none;
  border-bottom: 1px solid var(--color-border);
  outline: none;
  font-size: var(--font-size-standard);
  background: transparent;
  padding: 2px 0;
}
</style>
