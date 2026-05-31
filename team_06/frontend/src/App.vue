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



const tab = ref('brief')
const chatHistory = ref([])
const agentState = ref(null)
const parsedInput = ref(null)


function mockAgentResponse(messages) {
  // Simulate the described conversation and state updates
  const userMsgs = messages.filter(m => m.role === 'user').map(m => m.text.trim().toLowerCase());
  if (userMsgs.length === 0) {
    return {
      text: 'Hi, I am John, I live with my partner Sarah, we cook a lot',
      layout: null,
      parsedInput: null
    };
  }
  if (userMsgs.length === 1) {
    return {
      text: 'How many bedrooms do you want?',
      layout: null,
      parsedInput: {
        households: [
          { name: 'John', age: 34, relationship: 'self' },
          { name: 'Sarah', age: 32, relationship: 'partner' }
        ],
        activities: [
          { type: 'Cooking', time: 'often' }
        ],
        rooms: [],
        brief: 'John and Sarah, a couple who cook a lot.'
      }
    };
  }
  if (userMsgs.length === 2) {
    return {
      text: 'Here is a layout suggestion. Are you happy with this layout, or would you like to explore more options?',
      layout: {
        rooms: [
          { id: 1, geometry: [[0,0],[0,40],[40,40],[40,0]], attributes: { program: 'Bedroom 1', area: 16 } },
          { id: 2, geometry: [[50,0],[50,40],[90,40],[90,0]], attributes: { program: 'Bedroom 2', area: 16 } },
          { id: 3, geometry: [[0,50],[0,90],[90,90],[90,50]], attributes: { program: 'Living/Kitchen', area: 36 } }
        ]
      },
      parsedInput: {
        households: [
          { name: 'John', age: 34, relationship: 'self' },
          { name: 'Sarah', age: 32, relationship: 'partner' }
        ],
        activities: [
          { type: 'Cooking', time: 'often' }
        ],
        rooms: [
          { type: 'bedroom' },
          { type: 'bedroom' }
        ],
        brief: 'John and Sarah want 2 bedrooms and a large kitchen/living area.'
      }
    };
  }
  // Third user message: e.g. "I work from home, etc..."
  return {
    text: 'Here is an updated layout with a workspace. Anything else to add?',
    layout: {
      rooms: [
        { id: 1, geometry: [[0,0],[0,40],[40,40],[40,0]], attributes: { program: 'Bedroom 1', area: 16 } },
        { id: 2, geometry: [[50,0],[50,40],[90,40],[90,0]], attributes: { program: 'Bedroom 2', area: 16 } },
        { id: 3, geometry: [[0,50],[0,90],[90,90],[90,50]], attributes: { program: 'Living/Kitchen', area: 36 } },
        { id: 4, geometry: [[100,0],[100,30],[130,30],[130,0]], attributes: { program: 'Workspace', area: 9 } }
      ]
    },
    parsedInput: {
      households: [
        { name: 'John', age: 34, relationship: 'self' },
        { name: 'Sarah', age: 32, relationship: 'partner' }
      ],
      activities: [
        { type: 'Cooking', time: 'often' },
        { type: 'Work from home', time: 'weekdays' }
      ],
      rooms: [
        { type: 'bedroom' },
        { type: 'bedroom' },
        { type: 'workspace' }
      ],
      brief: 'John and Sarah want 2 bedrooms, a large kitchen/living area, and a workspace.'
    }
  };
}

function handleUserMessage(message) {
  // Add user message
  chatHistory.value.push({
    id: Date.now(),
    role: 'user',
    text: message,
    timestamp: new Date().toISOString()
  });

  setTimeout(() => {
    // Get new agent state/layout/parsedInput
    const agent = mockAgentResponse(chatHistory.value);
    if (agent) {
      agentState.value = agent.layout;
      parsedInput.value = agent.parsedInput;
      chatHistory.value.push({
        id: Date.now() + 1,
        role: 'agent',
        text: agent.text,
        timestamp: new Date().toISOString()
      });
    }
  }, 800);
}
</script>

<style src="./style.css"></style>

