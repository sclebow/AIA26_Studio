<template>
  <div id="app">
    <div class="app-layout">
      <Sidebar :tab="tab" @change="tab = $event" :index="currentIndex" />
      <WorkSpace :index="currentIndex" />
      <ChatPanel :chat="chatHistory" @send="handleUserMessage" :index="currentIndex" />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import Sidebar from './components/Sidebar.vue'
import ChatPanel from './components/ChatPanel.vue'
import WorkSpace from './components/WorkSpace.vue'
import agentResponses from './assets/dummy/agent_response.json'

const tab = ref('brief')
const chatHistory = ref([])
const currentIndex = ref(0)

function handleUserMessage(message) {
  // Add user message
  chatHistory.value.push({
    id: Date.now(),
    role: 'user',
    text: message,
    timestamp: new Date().toISOString()
  })

  // Add agent response after a short delay, using agentResponses[currentIndex]
  setTimeout(() => {
    if (agentResponses[currentIndex.value]) {
      chatHistory.value.push({
        id: Date.now() + 1,
        role: 'agent',
        text: agentResponses[currentIndex.value].text,
        timestamp: new Date().toISOString()
      })
      // Move to next index for next turn, but don't go out of bounds
      if (currentIndex.value < agentResponses.length - 1) {
        currentIndex.value += 1
      }
    }
  }, 800)
}
</script>

<style src="./style.css"></style>

