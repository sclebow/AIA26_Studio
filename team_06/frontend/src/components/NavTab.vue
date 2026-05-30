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

<style scoped>
.nav-tab {
  width: 68px;
  background: var(--color-grey-bg);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 24px;
  border-right: 1px solid var(--color-border);
}

.nav-header {
  font-size: var(--font-size-title);
  font-weight: 700;
  color: var(--color-blue);
  margin-bottom: 32px;
  letter-spacing: -1px;
}

.nav-tabs {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.nav-tab-btn {
  background: none;
  border: none;
  padding: 0;
  margin: 0;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  color: var(--color-text-secondary);
  font-size: var(--font-size-nav);
  transition: color 0.2s;
}

.nav-tab-btn.active {
  color: var(--color-blue);
}
</style>