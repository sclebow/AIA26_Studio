<script setup>
import logoUrl from '../assets/icons/inHabit_logo_small.svg'
</script>

<template>
  <div class="sidebar-header">
    <img :src="logoUrl" alt="inHabit logo" class="sidebar-logo" />
    <span class="sidebar-app-name">inHabit</span>
  </div>
</template>

<style scoped>
.sidebar-header {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 28px 28px 20px 28px;
  background: white;
  border-bottom: 1px solid var(--color-border);
}
.sidebar-logo {
  width: 40px;
  height: 40px;
  flex-shrink: 0;
}
.sidebar-app-name {
  font-size: var(--font-size-title);
  font-weight: 700;
  color: var(--color-blue);
  letter-spacing: -1px;
}
</style>
