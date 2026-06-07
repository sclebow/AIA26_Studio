<template>
  <div id="app">
    <div class="app-layout">
      <Sidebar :tab="tab" @change="tab = $event" :parsedInput="parsedInput" :history="layoutHistory" :agentState="agentState" @restore="handleRestore" />
      <WorkSpace :agentState="agentState" :parsedInput="parsedInput" @layoutLoaded="handleLayoutLoaded" />
      <ChatPanel :chat="chatHistory" @send="handleUserMessage" @newChat="handleNewChat" />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import Sidebar from './components/Sidebar.vue'
import ChatPanel from './components/ChatPanel.vue'
import WorkSpace from './components/WorkSpace.vue'
import { clearSession, restoreLayout, sendChatMessage, uploadBoundaryLayout } from './api/agentClient.js'

const tab = ref('brief')
const chatHistory = ref([])
const agentState = ref(null)
const parsedInput = ref(null)
const layoutHistory = ref([])

const boundary = ref(null)

// ─── Boundary upload ──────────────────────────────────────────────────────────
async function handleLayoutLoaded(json) {
  boundary.value = json

  try {
    await uploadBoundaryLayout(json)
  } catch (error) {
    chatHistory.value.push({
      id: Date.now(),
      role: 'agent',
      text: `Could not upload boundary layout: ${error.message}`,
      timestamp: new Date().toISOString()
    })
  }

  if (json) {
    agentState.value = {
      layoutId: json.layoutId || 'Boundary',
      outline: json.outline || json.apartment?.geometry || [],
      rooms: json.rooms || [],
      attributes: json.apartment?.attributes || {}
    }
  } else {
    agentState.value = null
  }
}

// ─── Shared applier ───────────────────────────────────────────────────────────
function applyAgentResponse(response) {
  if (response.brief !== undefined) parsedInput.value = response.brief
  if (response.layout) {
    agentState.value = response.layout
    layoutHistory.value.push({ ...response.layout, _savedAt: new Date().toISOString() })
    if (layoutHistory.value.length > 15) layoutHistory.value.shift()
  }
  chatHistory.value.push({
    id: Date.now(),
    role: 'agent',
    text: response.message,
    timestamp: new Date().toISOString()
  })
}

// ─── Chat path ────────────────────────────────────────────────────────────────
async function handleUserMessage(message) {
  chatHistory.value.push({ id: Date.now(), role: 'user', text: message, timestamp: new Date().toISOString() })

  try {
    const response = await sendChatMessage(message)
    applyAgentResponse(response)
  } catch (error) {
    chatHistory.value.push({
      id: Date.now(),
      role: 'agent',
      text: `Backend error: ${error.message}`,
      timestamp: new Date().toISOString()
    })
  }
}

// ─── New chat (full reset) ────────────────────────────────────────────────────
async function handleNewChat() {
  try {
    await clearSession()
  } catch (error) {
    chatHistory.value.push({
      id: Date.now(),
      role: 'agent',
      text: `Could not clear backend session: ${error.message}`,
      timestamp: new Date().toISOString()
    })
  }
  chatHistory.value = []
  agentState.value = null
  parsedInput.value = null
  boundary.value = null
  tab.value = 'brief'
}

// ─── Restore from history ─────────────────────────────────────────────────────
async function handleRestore(layout) {
  agentState.value = layout
  try {
    await restoreLayout(layout)
  } catch (error) {
    chatHistory.value.push({
      id: Date.now(),
      role: 'agent',
      text: `Could not restore layout in backend session: ${error.message}`,
      timestamp: new Date().toISOString()
    })
  }
}

// ─── Sidebar path ─────────────────────────────────────────────────────────────
</script>

<style src="./style.css"></style>

