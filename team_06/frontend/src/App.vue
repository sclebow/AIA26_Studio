<template>
  <div id="app">
    <div class="app-layout">
      <Sidebar :tab="tab" @change="tab = $event" :parsedInput="parsedInput" :history="layoutHistory" :agentState="agentState" @restore="handleRestore" />
      <WorkSpace :agentState="agentState" @layoutLoaded="handleLayoutLoaded" />
      <ChatPanel :chat="chatHistory" @send="handleUserMessage" />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import Sidebar from './components/Sidebar.vue'
import ChatPanel from './components/ChatPanel.vue'
import WorkSpace from './components/WorkSpace.vue'
import { getAgentResponse } from './mock/agentMock.js'

const tab = ref('brief')
const chatHistory = ref([])
const agentState = ref(null)
const parsedInput = ref(null)
const layoutHistory = ref([])

const boundary = ref(null)

// ─── Boundary upload ──────────────────────────────────────────────────────────
function handleLayoutLoaded(json) {
  boundary.value = json
  if (json) {
    // Use whatever is in the JSON directly — rooms, outline, everything
    agentState.value = {
      layoutId: json.layoutId || 'Boundary',
      outline: json.outline || json.apartment?.geometry || [],
      rooms: json.rooms || [],
      attributes: json.apartment?.attributes || {}
    }
    layoutHistory.value.push({ ...agentState.value, _savedAt: new Date().toISOString() })
  } else {
    // File cleared — remove layout
    agentState.value = null
  }
}

// ─── Shared applier ───────────────────────────────────────────────────────────
// Applies an AgentResponse onto local state.
// To connect a real agent, swap getAgentResponse/getAgentResponseForSidebarAdd
// with API calls that return the same shape — this function stays unchanged.
function applyAgentResponse(response) {
  if (response.parsedInput) parsedInput.value = response.parsedInput
  if (response.layout) {
    agentState.value = response.layout
    layoutHistory.value.push({ ...response.layout, _savedAt: new Date().toISOString() })
  }
  chatHistory.value.push({
    id: Date.now(),
    role: 'agent',
    text: response.message,
    timestamp: new Date().toISOString()
  })
}

// ─── Chat path ────────────────────────────────────────────────────────────────
function handleUserMessage(message) {
  chatHistory.value.push({ id: Date.now(), role: 'user', text: message, timestamp: new Date().toISOString() })
  setTimeout(() => {
    const response = getAgentResponse(message, { parsedInput: parsedInput.value, layout: agentState.value, boundary: boundary.value })
    applyAgentResponse(response)
  }, 800)
}

// ─── Restore from history ─────────────────────────────────────────────────────
function handleRestore(layout) {
  agentState.value = layout
}

// ─── Sidebar path ─────────────────────────────────────────────────────────────
</script>

<style src="./style.css"></style>

