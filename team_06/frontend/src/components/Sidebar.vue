
<script setup>
import SidebarHeader from './SidebarHeader.vue'
import SidebarBrief from './SidebarBrief.vue'
import SidebarHistory from './SidebarHistory.vue'
import SidebarExplore from './SidebarExplore.vue'

const props = defineProps({
  tab: String,
  parsedInput: { type: Object, default: null },
  history: { type: Array, default: () => [] },
  agentState: { type: Object, default: null }
})
const emit = defineEmits(['change', 'restore'])
</script>

<template>
  <aside class="sidebar">
    <SidebarHeader :tab="props.tab" @change="emit('change', $event)" />
    <div class="sidebar-content">
      <SidebarBrief v-if="props.tab === 'brief'" :parsedInput="props.parsedInput" />
      <SidebarExplore v-else-if="props.tab === 'explore'" />
      <SidebarHistory v-else :history="props.history" :agentState="props.agentState" @restore="emit('restore', $event)" />
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 310px;
  min-width: 310px;
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
  padding: 38px 28px 0px 28px;
  overflow-y: auto;
}
</style>


