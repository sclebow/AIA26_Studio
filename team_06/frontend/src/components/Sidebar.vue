
<script setup>
import { ref, nextTick } from 'vue'
import userIcon from '../assets/icons/user.svg'
import clockIcon from '../assets/icons/clock.svg'
import boxIcon from '../assets/icons/box.svg'
import messageIcon from '../assets/icons/message.svg'
import plusIcon from '../assets/icons/plus.svg'
import SidebarHeader from './SidebarHeader.vue'

const props = defineProps({
  tab: String,
  parsedInput: {
    type: Object,
    default: null
  }
})
const emit = defineEmits(['change', 'itemAdded', 'reset'])

const addingTo = ref(null) // 'households' | 'activities' | 'rooms'
const newItemText = ref('')
const inputRef = ref(null)

async function startAdding(section) {
  addingTo.value = section
  newItemText.value = ''
  await nextTick()
  inputRef.value?.focus()
}

function confirmAdd() {
  const val = newItemText.value.trim()
  if (!val) { cancelAdd(); return }
  if (addingTo.value === 'households') {
    emit('itemAdded', { section: 'households', item: { name: val } })
  } else if (addingTo.value === 'activities') {
    emit('itemAdded', { section: 'activities', item: { type: val } })
  } else if (addingTo.value === 'rooms') {
    emit('itemAdded', { section: 'rooms', item: { name: val, id: Date.now() } })
  } else if (addingTo.value === 'extras') {
    emit('itemAdded', { section: 'extras', item: val })
  }
  cancelAdd()
}

function cancelAdd() {
  addingTo.value = null
  newItemText.value = ''
}

function onKeydown(e) {
  if (e.key === 'Enter') confirmAdd()
  else if (e.key === 'Escape') cancelAdd()
}
</script>

<template>
  <aside class="sidebar">
    <SidebarHeader :tab="props.tab" @change="emit('change', $event)" />
    <div class="sidebar-content">
      <template v-if="props.tab==='brief'">
        <section class="sidebar-section">
          <div class="sidebar-section-title">
            <img :src="userIcon" alt="Households" width="20" height="20" />
            Households
            <button class="sidebar-title-add" @click="startAdding('households')"><img :src="plusIcon" width="14" height="14" alt="add" /></button>
          </div>
          <ul class="sidebar-list">
            <li v-if="props.parsedInput && props.parsedInput.households && props.parsedInput.households.length" v-for="(h, i) in props.parsedInput.households" :key="i">
              {{ h.name }}<span v-if="h.age && h.age !== 'int'"> - {{ h.age }}</span><span v-if="h.relationship"> - {{ h.relationship }}</span>
            </li>
            <li v-else-if="addingTo !== 'households'">No input yet</li>
            <li v-if="addingTo === 'households'" class="sidebar-list-input-row">
              <input ref="inputRef" v-model="newItemText" class="sidebar-list-input" placeholder="Name..." @keydown="onKeydown" @blur="cancelAdd" />
            </li>
          </ul>
        </section>
        <section class="sidebar-section">
          <div class="sidebar-section-title">
            <img :src="clockIcon" alt="Routine" width="20" height="20" />
            Routine
            <button class="sidebar-title-add" @click="startAdding('activities')"><img :src="plusIcon" width="14" height="14" alt="add" /></button>
          </div>
          <ul class="sidebar-list">
            <li v-if="props.parsedInput && props.parsedInput.activities && props.parsedInput.activities.length" v-for="(a, i) in props.parsedInput.activities" :key="i">
              {{ a.type }}<span v-if="a.time && a.time !== 'int'"> - {{ a.time }}</span>
            </li>
            <li v-else-if="addingTo !== 'activities'">No input yet</li>
            <li v-if="addingTo === 'activities'" class="sidebar-list-input-row">
              <input ref="inputRef" v-model="newItemText" class="sidebar-list-input" placeholder="Activity..." @keydown="onKeydown" @blur="cancelAdd" />
            </li>
          </ul>
        </section>
        <section class="sidebar-section">
          <div class="sidebar-section-title">
            <img :src="boxIcon" alt="Rooms" width="20" height="20" />
            Rooms
            <button class="sidebar-title-add" @click="startAdding('rooms')"><img :src="plusIcon" width="14" height="14" alt="add" /></button>
          </div>
          <ul class="sidebar-list">
            <li v-if="props.parsedInput && props.parsedInput.rooms && props.parsedInput.rooms.length" v-for="(r, i) in props.parsedInput.rooms" :key="i">
              {{ r.name || r.attributes?.program || 'Room ' + r.id }}<span v-if="r.size"> - {{ r.size }}</span>
            </li>
            <li v-else-if="addingTo !== 'rooms'">No input yet</li>
            <li v-if="addingTo === 'rooms'" class="sidebar-list-input-row">
              <input ref="inputRef" v-model="newItemText" class="sidebar-list-input" placeholder="Room name..." @keydown="onKeydown" @blur="cancelAdd" />
            </li>
          </ul>
        </section>
        <section class="sidebar-section">
          <div class="sidebar-section-title">
            <img :src="messageIcon" alt="Extra" width="20" height="20" />
            Extra
            <button class="sidebar-title-add" @click="startAdding('extras')"><img :src="plusIcon" width="14" height="14" alt="add" /></button>
          </div>
          <ul class="sidebar-list">
            <li v-if="props.parsedInput && props.parsedInput.extras && props.parsedInput.extras.length" v-for="(e, i) in props.parsedInput.extras" :key="i">
              {{ e }}
            </li>
            <li v-else-if="addingTo !== 'extras'">No input yet</li>
            <li v-if="addingTo === 'extras'" class="sidebar-list-input-row">
              <input ref="inputRef" v-model="newItemText" class="sidebar-list-input" placeholder="e.g. We have a dog..." @keydown="onKeydown" @blur="cancelAdd" />
            </li>
          </ul>
        </section>
      </template>
      <template v-else-if="props.tab==='explore'">
        <div class="sidebar-section-title">Explore (placeholder)</div>
      </template>
      <template v-else>
        <div class="sidebar-section-title">History (placeholder)</div>
      </template>
    </div>
    <button class="reset-btn default-btn" @click="emit('reset')">Reset</button>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 300px;
  min-width: 300px;
  background: white;
  display: flex;
  flex-direction: column;
  height: 100vh;
}
.sidebar-content {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  gap: 32px;
  padding: 38px 20px 0px 20px;
  overflow-y: auto;
}

.sidebar-section {
  margin-bottom: 12px;
}

.sidebar-section-title {
  display: flex;
  align-items: center;
  font-size: var(--font-size-bold);
  font-weight: 600;
  margin-bottom: 24px;
  color: var(--color-text-primary);
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

.sidebar-title-add:hover {
  opacity: 1;
}

.sidebar-list {
  margin: 0 0 0 28px;
  padding: 0;
  list-style: none;
  color: var(--color-text);
  font-size: var(--font-size-standard);
}

.sidebar-list-input-row {
  list-style: none;
}

.sidebar-list-input {
  width: 100%;
  border: none;
  border-bottom: 1px solid var(--color-border);
  outline: none;
  font-size: var(--font-size-standard);
  color: var(--color-text);
  background: transparent;
  padding: 2px 0;
}

.reset-btn{
    margin-bottom: 28px;
}

</style>


