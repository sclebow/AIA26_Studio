<template>
  <div id="app">
    <div class="app-layout">
      <Sidebar :tab="tab" @change="tab = $event" :parsedInput="parsedInput" @itemAdded="handleItemAdded" @reset="handleReset" />
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
import { getAgentResponse, getAgentResponseForSidebarAdd, generateBrief } from './mock/agentMock.js'

const tab = ref('brief')
const chatHistory = ref([])
const agentState = ref(null)
const parsedInput = ref(null)

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
  if (response.layout)      agentState.value  = response.layout
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

// ─── Reset ───────────────────────────────────────────────────────────────────
function handleReset() {
  parsedInput.value = null

  if (boundary.value) {
    agentState.value = {
      layoutId: boundary.value.layoutId || 'Boundary',
      outline: boundary.value.outline || boundary.value.apartment?.geometry || [],
      rooms: [],
      attributes: boundary.value.apartment?.attributes || {}
    }
  } else {
    agentState.value = null
  }
}

// ─── Sidebar path ─────────────────────────────────────────────────────────────
function handleItemAdded({ section, item }) {
  // 1. Merge item into local state immediately (optimistic update)
  const base = parsedInput.value ?? { households: [], activities: [], rooms: [], extras: [] }
  const merged = { ...base, [section]: [...(base[section] ?? []), item] }
  // brief is internal-only (agent context), not displayed
  merged.brief = generateBrief(merged)
  parsedInput.value = merged

  // 2. Ask mock (or real agent) for acknowledgement + optional layout update
  setTimeout(() => {
    const response = getAgentResponseForSidebarAdd(section, item, {
      parsedInput: parsedInput.value,
      layout: agentState.value
    })
    applyAgentResponse(response)
  }, 400)
}
</script>

<style src="./style.css"></style>

