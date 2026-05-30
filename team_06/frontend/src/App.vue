

<template>
  <div id="app">
    <div class="app-layout">
      <Sidebar :tab="tab" @change="tab = $event" />
      <ChatPanel />
      <RightPanel />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import Sidebar from './components/Sidebar.vue'
import ChatPanel from './components/ChatPanel.vue'
import RightPanel from './components/RightPanel.vue'

const tab = ref('create')
</script>

<style src="./style.css"></style>

