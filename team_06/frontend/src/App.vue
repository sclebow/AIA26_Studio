<template>
  <div id="app">
    <div class="app-layout">
      <Sidebar :tab="tab" @change="tab = $event" :parsedInput="parsedInput" :history="layoutHistory" :agentState="agentState" @restore="handleRestore" />
      <WorkSpace :agentState="agentState" :parsedInput="parsedInput" @layoutLoaded="handleLayoutLoaded" />
      <ChatPanel :chat="chatHistory" :isBusy="isSending" @send="handleUserMessage" @newChat="handleNewChat" />
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import Sidebar from './components/Sidebar.vue'
import ChatPanel from './components/ChatPanel.vue'
import WorkSpace from './components/WorkSpace.vue'
import { clearSession, restoreLayout, sendChatMessage, startFreshSession, uploadBoundaryLayout } from './api/agentClient.js'

const tab = ref('brief')
const chatHistory = ref([])
const agentState = ref(null)
const parsedInput = ref(null)
const layoutHistory = ref([])
const isSending = ref(false)

const boundary = ref(null)

function pushChatMessage(role, text, extra = {}) {
  const id = `${Date.now()}-${chatHistory.value.length}-${role}`
  chatHistory.value.push({
    id,
    role,
    text,
    timestamp: new Date().toISOString(),
    ...extra
  })
  return id
}

function updateChatMessage(id, text, extra = {}) {
  const target = chatHistory.value.find(message => message.id === id)
  if (target) {
    target.text = text
    Object.assign(target, extra)
  }
}

function removeChatMessage(id) {
  chatHistory.value = chatHistory.value.filter(message => message.id !== id)
}

function clearBoundaryUploadErrors() {
  chatHistory.value = chatHistory.value.filter(message => message.text !== 'Could not upload boundary layout: Failed to fetch' && !message.text.startsWith('Could not upload boundary layout: Request failed with status'))
}

function formatStatusMessages(messages) {
  if (!messages?.length) return 'Thinking'
  return messages[messages.length - 1]
}

onMounted(async () => {
  await startFreshSession()
  chatHistory.value = []
  agentState.value = null
  parsedInput.value = null
  boundary.value = null
})

async function handleLayoutLoaded(json) {
  boundary.value = json

  try {
    await uploadBoundaryLayout(json)
    clearBoundaryUploadErrors()
  } catch (error) {
    pushChatMessage('agent', `Could not upload boundary layout: ${error.message}`)
  }

  if (json) {
    agentState.value = {
      layoutId: json.layoutId || 'Boundary',
      outline: json.outline || json.apartment?.geometry || [],
      rooms: json.rooms || [],
      attributes: json.apartment?.attributes || {},
      evaluation: null
    }
  } else {
    agentState.value = null
  }
}

function applyAgentResponse(response) {
  if (response.brief !== undefined) parsedInput.value = response.brief
  if (response.layout) {
    const layoutWithEvaluation = { ...response.layout, evaluation: response.evaluation ?? null }
    agentState.value = layoutWithEvaluation
    layoutHistory.value.push({ ...layoutWithEvaluation, _savedAt: new Date().toISOString() })
    if (layoutHistory.value.length > 15) layoutHistory.value.shift()
  }
  pushChatMessage('agent', response.message)
}

async function handleUserMessage(message) {
  if (isSending.value) return

  pushChatMessage('user', message)
  const statusMessageId = pushChatMessage('status', 'Thinking', { isLoading: true })
  isSending.value = true

  try {
    const response = await sendChatMessage(message, messages => {
      updateChatMessage(statusMessageId, formatStatusMessages(messages), { isLoading: true })
    })
    removeChatMessage(statusMessageId)
    applyAgentResponse(response)
  } catch (error) {
    updateChatMessage(statusMessageId, 'Request failed', { isLoading: false, tone: 'error' })
    pushChatMessage('agent', `Backend error: ${error.message}`)
  } finally {
    isSending.value = false
  }
}

async function handleNewChat() {
  try {
    await clearSession()
  } catch (error) {
    pushChatMessage('agent', `Could not clear backend session: ${error.message}`)
  }
  chatHistory.value = []
  agentState.value = null
  parsedInput.value = null
  boundary.value = null
  tab.value = 'brief'
}

async function handleRestore(layout) {
  agentState.value = layout
  try {
    await restoreLayout(layout)
  } catch (error) {
    pushChatMessage('agent', `Could not restore layout in backend session: ${error.message}`)
  }
}
</script>

<style src="./style.css"></style>

