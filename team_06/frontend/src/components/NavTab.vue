<script setup>
defineProps({ tab: String })
</script>

<template>
  <nav class="nav-tab">
    <div class="nav-header">InHabit</div>
    <div class="nav-tabs">
      <button class="nav-tab-btn" :class="{active: tab==='create'}" @click="$emit('change', 'create')">
        <span>Create</span>
      </button>
      <button class="nav-tab-btn" :class="{active: tab==='explore'}" @click="$emit('change', 'explore')">
        <span>Explore</span>
      </button>
      <button class="nav-tab-btn" :class="{active: tab==='history'}" @click="$emit('change', 'history')">
        <span>History</span>
      </button>
    </div>
  </nav>
</template>

