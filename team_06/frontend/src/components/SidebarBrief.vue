<script setup>
import boxIcon from '../assets/icons/box.svg'
import messageIcon from '../assets/icons/message.svg'
import userIcon from '../assets/icons/user.svg'

const props = defineProps({
  parsedInput: { type: Object, default: null }
})
</script>

<template>
  <section class="sidebar-section">
    <div class="sidebar-section-title">
      <img :src="messageIcon" alt="Description" width="20" height="20" style="opacity:0.6;" />
      Description
    </div>
    <ul class="sidebar-list">
      <template v-if="props.parsedInput?.description || props.parsedInput?.summary">
        <li>{{ props.parsedInput.description || props.parsedInput.summary }}</li>
      </template>
      <li v-else>No brief details yet</li>
    </ul>
  </section>

  <section class="sidebar-section">
    <div class="sidebar-section-title">
      <img :src="boxIcon" alt="Rooms" width="20" height="20" style="opacity:0.6;" />
      Rooms
    </div>
    <ul class="sidebar-list">
      <template v-if="props.parsedInput?.rooms?.length">
        <li v-for="(room, i) in props.parsedInput.rooms" :key="i">
          {{ room.label || room.name }}
        </li>
      </template>
      <li v-else>No rooms requested yet</li>
    </ul>
  </section>

  <section class="sidebar-section">
    <div class="sidebar-section-title">
      <img :src="userIcon" alt="Connections" width="20" height="20" style="opacity:0.6;" />
      Connections
    </div>
    <ul class="sidebar-list">
      <template v-if="props.parsedInput?.access?.length || props.parsedInput?.adjacency?.length || props.parsedInput?.separation?.length">
        <li v-for="(pair, i) in props.parsedInput.access ?? []" :key="`access-${i}`">
          Access: {{ pair }}
        </li>
        <li v-for="(pair, i) in props.parsedInput.adjacency ?? []" :key="`adjacency-${i}`">
          Adjacent: {{ pair }}
        </li>
        <li v-for="(pair, i) in props.parsedInput.separation ?? []" :key="`separation-${i}`">
          Separate: {{ pair }}
        </li>
      </template>
      <li v-else>No room relationships yet</li>
    </ul>
  </section>

  <section class="sidebar-section">
    <div class="sidebar-section-title">
      <img :src="messageIcon" alt="Extra" width="20" height="20" style="opacity:0.6;" />
      Routine
    </div>
    <ul class="sidebar-list">
      <li>Disabled for now</li>
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
