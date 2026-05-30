<script setup>
import { ref } from 'vue'
import userIcon from '../assets/user.svg'
import clockIcon from '../assets/clock.svg'
import boxIcon from '../assets/box.svg'
import messageIcon from '../assets/message.svg'
const count = ref(0)

defineProps({ tab: String })

</script>

<template>
  <aside class="sidebar">
    <template v-if="tab==='create'">
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
    <template v-else-if="tab==='explore'">
      <div class="sidebar-section-title">Explore (placeholder)</div>
    </template>
    <template v-else>
      <div class="sidebar-section-title">History (placeholder)</div>
    </template>
  </aside>
</template>


