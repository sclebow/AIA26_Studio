<template>
  <div class="sidebar-header">
    <span class="sidebar-app-name">InHabit</span>
    <div class="sidebar-nav-tabs">
      <button class="sidebar-nav-tab-btn" :class="{active: tab==='create'}" @click="$emit('change', 'create')">Create</button>
      <button class="sidebar-nav-tab-btn" :class="{active: tab==='explore'}" @click="$emit('change', 'explore')">Explore</button>
      <button class="sidebar-nav-tab-btn" :class="{active: tab==='history'}" @click="$emit('change', 'history')">History</button>
    </div>
  </div>
</template>

<script setup>
defineProps({ tab: String })
</script>
