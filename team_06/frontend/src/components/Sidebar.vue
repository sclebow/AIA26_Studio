
<script setup>
import userIcon from '../assets/user.svg'
import clockIcon from '../assets/clock.svg'
import boxIcon from '../assets/box.svg'
import messageIcon from '../assets/message.svg'
import SidebarHeader from './SidebarHeader.vue'
const props = defineProps({ tab: String })
const emit = defineEmits(['change'])
</script>

<template>
  <aside class="sidebar">
    <SidebarHeader :tab="props.tab" @change="emit('change', $event)" />
    <div class="sidebar-content">
      <template v-if="props.tab==='create'">
        <section class="sidebar-section">
          <div class="sidebar-section-title">
            <img :src="userIcon" alt="Households" width="20" height="20" />
            Households
          </div>
          <ul class="sidebar-list">
            <li>Mark - 36</li>
            <li>Sara - 32</li>
            <li>Johnny - 2</li>
          </ul>
        </section>
        <section class="sidebar-section">
          <div class="sidebar-section-title">
            <img :src="clockIcon" alt="Routine" width="20" height="20" />
            Routine
          </div>
          <ul class="sidebar-list">
            <li>Morning - work</li>
            <li>Afternoon - work</li>
            <li>Evening - cook</li>
          </ul>
        </section>
        <section class="sidebar-section">
          <div class="sidebar-section-title">
            <img :src="boxIcon" alt="Rooms" width="20" height="20" />
            Rooms
          </div>
          <ul class="sidebar-list">
            <li>Bedroom - large</li>
            <li>Bathroom - small</li>
            <li>Foyer</li>
          </ul>
        </section>
        <section class="sidebar-section">
          <div class="sidebar-section-title">
            <img :src="messageIcon" alt="Brief" width="20" height="20" />
            Brief
          </div>
          <div class="sidebar-brief">
            For the user, natural light is more important than the size of the room...
          </div>
        </section>
        <button class="create-layout-btn">Create Layout</button>
      </template>
      <template v-else-if="props.tab==='explore'">
        <div class="sidebar-section-title">Explore (placeholder)</div>
      </template>
      <template v-else>
        <div class="sidebar-section-title">History (placeholder)</div>
      </template>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 320px;
  min-width: 320px;
  background: var(--color-grey-bg);
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--color-border);
  height: 100vh;
}


.sidebar-content {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  gap: 28px;
  padding: 24px 20px 24px 20px;
  overflow-y: auto;
}

.sidebar-section {
  margin-bottom: 12px;
}

.sidebar-section-title {
  display: flex;
  align-items: center;
  font-size: var(--font-size-nav);
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--color-text-secondary);
  gap: 8px;
}

.sidebar-list {
  margin: 0 0 0 24px;
  padding: 0;
  list-style: none;
  color: var(--color-text);
  font-size: var(--font-size-standard);
}

.sidebar-brief {
  background: var(--color-white);
  border-radius: var(--radius);
  padding: 14px 16px;
  font-size: var(--font-size-standard);
  color: var(--color-text-secondary);
  margin-bottom: 12px;
  box-shadow: var(--shadow-card);
}
.create-layout-btn {
  margin-top: auto;
  background: var(--gradient-btn);
  color: var(--color-white);
  font-weight: 600;
  font-size: var(--font-size-standard);
  border: none;
  border-radius: var(--radius);
  width: 180px;
  height: 44px;
  min-width: 180px;
  min-height: 44px;
  padding: 0;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(33, 118, 255, 0.10);
  transition: box-shadow 0.2s;
  display: block;
  margin-left: auto;
  margin-right: auto;
}
.create-layout-btn:hover {
  box-shadow: 0 4px 16px rgba(33, 118, 255, 0.18);
}
</style>


