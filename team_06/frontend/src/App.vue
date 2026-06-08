<template>
  <div id="app">
    <div class="app-layout">
      <Sidebar :tab="tab" @change="handleTabChange" :parsedInput="parsedInput" :history="layoutHistory" :exploreResults="exploreResults" :agentState="agentState" @restore="handleRestore" @selectCandidate="handleSelectCandidate" />
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
const exploreResults = ref([])
const isSending = ref(false)
const hasUserSelectedTab = ref(false)
const suppressAncillaryPartials = ref(false)

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

function attachExploreResults(layout) {
  if (!layout) return null
  return {
    ...layout,
    searchResults: exploreResults.value
  }
}

function attachRoutine(layout, routine = null) {
  if (!layout) return null
  return {
    ...layout,
    routine: routine ?? layout.routine ?? null
  }
}

function isSameLayout(nextLayout, currentLayout) {
  if (!nextLayout || !currentLayout) return false
  return Boolean(nextLayout.layoutId) && nextLayout.layoutId === currentLayout.layoutId
}

function handleTabChange(nextTab) {
  hasUserSelectedTab.value = true
  tab.value = nextTab
}

function applySearchResults(searchResults) {
  exploreResults.value = Array.isArray(searchResults) ? searchResults : []
  if (!hasUserSelectedTab.value && exploreResults.value.length > 0) {
    tab.value = 'explore'
  }
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
    agentState.value = attachRoutine(attachExploreResults({
      layoutId: json.layoutId || 'Boundary',
      outline: json.outline || json.apartment?.geometry || [],
      rooms: json.rooms || [],
      attributes: json.apartment?.attributes || {},
      evaluation: null
    }), null)
  } else {
    agentState.value = null
  }
}

function applyAgentResponse(response) {
  if (response.brief !== undefined) parsedInput.value = response.brief
  if (response.search_results !== undefined) {
    applySearchResults(response.search_results)
  }
  if (response.layout) {
    const layoutWithEvaluation = attachRoutine(
      attachExploreResults({ ...response.layout, evaluation: response.evaluation ?? null }),
      response.routine ?? null
    )
    agentState.value = layoutWithEvaluation
    layoutHistory.value.push({ ...layoutWithEvaluation, _savedAt: new Date().toISOString() })
    if (layoutHistory.value.length > 15) layoutHistory.value.shift()
  } else if (agentState.value) {
    agentState.value = attachRoutine(attachExploreResults(agentState.value), response.routine ?? agentState.value.routine ?? null)
  }
  pushChatMessage('agent', response.message)
}

function applyPartialResponse(response) {
  if (!response) return

  if (response.brief !== undefined) parsedInput.value = response.brief
  if (response.search_results !== undefined) {
    applySearchResults(response.search_results)
  }
  if (response.layout) {
    const sameLayout = isSameLayout(response.layout, agentState.value)
    agentState.value = attachRoutine(attachExploreResults({
      ...response.layout,
      evaluation: suppressAncillaryPartials.value
        ? null
        : response.evaluation ?? (sameLayout ? agentState.value?.evaluation ?? null : null)
    }), suppressAncillaryPartials.value ? null : response.routine ?? (sameLayout ? agentState.value?.routine ?? null : null))
  } else if (response.routine && agentState.value && !suppressAncillaryPartials.value) {
    agentState.value = attachRoutine(attachExploreResults(agentState.value), response.routine)
  } else if (response.evaluation && agentState.value && !suppressAncillaryPartials.value) {
    agentState.value = attachRoutine(attachExploreResults({
      ...agentState.value,
      evaluation: response.evaluation
    }), response.routine ?? agentState.value?.routine ?? null)
  } else if (agentState.value && !suppressAncillaryPartials.value) {
    agentState.value = attachRoutine(attachExploreResults(agentState.value), response.routine ?? agentState.value?.routine ?? null)
  }
}

async function handleUserMessage(message) {
  if (isSending.value) return

  hasUserSelectedTab.value = false
  tab.value = 'brief'
  pushChatMessage('user', message)
  const statusMessageId = pushChatMessage('status', 'Thinking', { isLoading: true })
  isSending.value = true

  try {
    const response = await sendChatMessage(message, ({ statusMessages, partialResult }) => {
      updateChatMessage(statusMessageId, formatStatusMessages(statusMessages), { isLoading: true })
      applyPartialResponse(partialResult)
    })
    removeChatMessage(statusMessageId)
    suppressAncillaryPartials.value = false
    applyAgentResponse(response)
  } catch (error) {
    suppressAncillaryPartials.value = false
    updateChatMessage(statusMessageId, 'Request failed', { isLoading: false, tone: 'error' })
    pushChatMessage('agent', `Backend error: ${error.message}`)
  } finally {
    suppressAncillaryPartials.value = false
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
  exploreResults.value = []
  boundary.value = null
  hasUserSelectedTab.value = false
  tab.value = 'brief'
}

async function handleRestore(layout) {
  agentState.value = attachExploreResults(layout)
  try {
    await restoreLayout(agentState.value)
  } catch (error) {
    pushChatMessage('agent', `Could not restore layout in backend session: ${error.message}`)
  }
}

async function handleSelectCandidate(candidate) {
  if (!candidate?.layoutId || isSending.value) return
  if (agentState.value?.layoutId !== candidate.layoutId) {
    suppressAncillaryPartials.value = true
    const candidateLayout = candidate.layout
      ? {
          ...candidate.layout,
          layoutId: candidate.layoutId,
          evaluation: null
        }
      : null

    agentState.value = attachRoutine(
      attachExploreResults(candidateLayout),
      null
    )
  }
  await handleUserMessage(`select layout ${candidate.layoutId}`)
}
</script>

<style src="./style.css"></style>

