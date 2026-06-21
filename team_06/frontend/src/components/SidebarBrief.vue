<script setup>
import boxIcon from '../assets/icons/box.svg'
import messageIcon from '../assets/icons/message.svg'
import userIcon from '../assets/icons/user.svg'
import { computed } from 'vue'
import { formatRoomProgram } from '../utils/roomAnalysis.js'

const props = defineProps({
  parsedInput: { type: Object, default: null }
})

const roomChips = computed(() => {
  const rooms = Array.isArray(props.parsedInput?.rooms) ? props.parsedInput.rooms : []
  return rooms
    .filter((room) => typeof room?.name === 'string' && typeof room?.count === 'number' && room.count > 0)
    .map((room) => formatRoomProgram(room.name, room.count))
})

const householdChips = computed(() => {
  const household = Array.isArray(props.parsedInput?.household) ? props.parsedInput.household : []
  return household
    .map((member) => {
      if (!member || typeof member !== 'object') return ''
      const name = typeof member.name === 'string' ? member.name.trim() : ''
      const relationship = typeof member.relationship === 'string' ? member.relationship.trim() : ''
      if (name) return name
      if (relationship) return relationship
      return ''
    })
    .filter(Boolean)
})

const specificationText = computed(() => {
  const value = props.parsedInput?.description || props.parsedInput?.summary || ''
  return typeof value === 'string' ? value.trim() : ''
})

const specificationChips = computed(() => {
  if (Array.isArray(props.parsedInput?.specifications)) {
    return props.parsedInput.specifications
      .filter((item) => typeof item === 'string')
      .map((item) => item.trim())
      .filter(Boolean)
  }

  const value = specificationText.value
  if (!value || value.length > 60) return []

  const parts = value
    .split(/[,;]|\s+and\s+/i)
    .map((part) => part.trim())
    .filter(Boolean)

  if (!parts.length || parts.some((part) => part.length > 32)) {
    return value ? [value] : []
  }

  return parts
})

const useSpecificationBlock = computed(() => {
  if (!specificationText.value) return false
  if (!specificationChips.value.length) return true
  return specificationChips.value.length > 4 || specificationChips.value.some((chip) => chip.length > 36)
})
</script>

<template>


  

  <section class="sidebar-section">
    <div class="sidebar-section-title">
      <img :src="userIcon" alt="Households" width="20" height="20" style="opacity:0.6;" />
      Households
    </div>
    <div v-if="householdChips.length" class="spec-chip-list">
      <span v-for="chip in householdChips" :key="chip" class="spec-chip">{{ chip }}</span>
    </div>
    <ul v-else class="sidebar-list">
      <li class="sidebar-empty-text">No households yet</li>
    </ul>
  </section>
  <section class="sidebar-section">
    <div class="sidebar-section-title">
      <img :src="boxIcon" alt="Rooms" width="20" height="20" style="opacity:0.6;" />
      Rooms
    </div>
    <div v-if="roomChips.length" class="room-chip-list">
      <span v-for="chip in roomChips" :key="chip" class="room-chip">{{ chip }}</span>
    </div>
    <ul v-else class="sidebar-list">
      <li class="sidebar-empty-text">No rooms requested yet</li>
    </ul>
  </section>
    <section class="sidebar-section">
    <div class="sidebar-section-title">
      <img :src="messageIcon" alt="Specifications" width="20" height="20" style="opacity:0.6;" />
      Specifications
    </div>
      <div v-if="specificationChips.length && !useSpecificationBlock" class="spec-chip-list">
        <span v-for="chip in specificationChips" :key="chip" class="spec-chip">{{ chip }}</span>
      </div>
      <div v-else-if="specificationText" class="spec-block-list">
        <div class="spec-block">{{ specificationText }}</div>
      </div>
      <ul v-else class= "sidebar-empty-text">No specifications yet
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
  margin-bottom: 20px;
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
.sidebar-empty-text {
  font-size: var(--font-size-small);
  color: var(--color-text-secondary);
  font-style: italic;
}
.room-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.room-chip {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: 999px;
  background: var(--color-light-blue);
  color: var(--color-text-primary);
  font-size: var(--font-size-small);
  font-weight: 500;
  line-height: 1.2;
}
.spec-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.spec-block-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.spec-block {
  display: block;
  width: fit-content;
  max-width: 100%;
  padding: 8px 12px;
  border-radius: 16px;
  background: #f5f7fa;
  color: var(--color-text-primary);
  font-size: var(--font-size-small);
  font-weight: 500;
  line-height: 1.4;
  border: 1px solid var(--color-border);
  white-space: normal;
  overflow-wrap: anywhere;
}
.spec-chip {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: 999px;
  background: #f5f7fa;
  color: var(--color-text-primary);
  font-size: var(--font-size-small);
  font-weight: 500;
  line-height: 1.2;
  border: 1px solid var(--color-border);
}
</style>
