<template>
  <div id="app">
    <div class="app-layout">
      <Sidebar :tab="tab" @change="tab = $event" :parsedInput="parsedInput" @itemAdded="handleItemAdded" />
      <WorkSpace :agentState="agentState" />
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
    const response = getAgentResponse(message, { parsedInput: parsedInput.value, layout: agentState.value })
    applyAgentResponse(response)
  }, 800)
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

