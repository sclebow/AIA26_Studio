<script setup>
defineProps({ tab: String })
</script>

<template>
  <div class="sidebar-header">
    <span class="sidebar-app-name">InHabit</span>
    <div class="sidebar-nav-tabs">
      <button class="sidebar-nav-tab-btn" :class="{active: tab==='brief'}" @click="$emit('change', 'brief')">Brief</button>
      <button class="sidebar-nav-tab-btn" :class="{active: tab==='explore'}" @click="$emit('change', 'explore')">Explore</button>
      <button class="sidebar-nav-tab-btn" :class="{active: tab==='history'}" @click="$emit('change', 'history')">History</button>
    </div>
  </div>
</template>

<style scoped>  
.sidebar-header {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 28px 20px 0 20px;
  min-height: 64px;
  background: white;
  border-bottom: 1px solid var(--color-border);
}
.sidebar-app-name {
  font-size: var(--font-size-title);
  font-weight: 700;
  color: var(--color-blue);
  letter-spacing: -1px;
  margin-bottom: 18px;
}
.sidebar-nav-tabs {
  display: flex;
  flex-direction: row;
  gap: 18px;
  width: 100%;
}
.sidebar-nav-tab-btn {
  background: none;
  border: none;
  color: var(--color-text-secondary);
  font-size: var(--font-size-subtitle);
  padding: 0 10px;
  height: 36px;
  border-radius: 0;
  position: relative;
  cursor: pointer;
  transition: color 0.2s;
  display: flex;
  align-items: center;
}
.sidebar-nav-tab-btn.active {
  color: var(--color-blue);
}
.sidebar-nav-tab-btn.active::after {
  content: '';
  display: block;
  position: absolute;
  left: 0px;
  right: 0px;
  bottom: 0;
  height: 2.5px;
  background: var(--color-blue);
}
</style>


