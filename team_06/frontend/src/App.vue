<template>
  <div id="app">
    <div class="app-layout">
      <Sidebar :tab="tab" @change="tab = $event" :parsedInput="parsedInput" />
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
        rooms: [
          { id: 1, name: 'Kitchen' , size: 'large' }
        ],
        brief: 'John and Sarah area a couple and cook a lot.'
      }
    };
  }
  if (userMsgs.length === 2) {
    return {
      text: 'Here is a layout suggestion. Are you happy with this layout, or would you like to explore more options?',
      layout: {
        layoutId: 'Layout 1',
        rooms: [
          { id: 1, name: 'Bedroom', geometry: [[0,0],[0,40],[40,40],[40,0]], attributes: { program: 'bedroom', area: 16 } },
          { id: 2, name: 'Kitchen', geometry: [[50,0],[50,40],[90,40],[90,0]], attributes: { program: 'kitchen', area: 16 } },
          { id: 3, name: 'Living', geometry: [[0,50],[0,90],[90,90],[90,50]], attributes: { program: 'living', area: 36 } }
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
          { id: 1, name: 'Kitchen' , size: 'large' },
          { id: 2, name: 'Bedroom' , size: 'double'}
        ],
        brief: 'John and Sarah area a couple and cook a lot. They want one bedroom.'
      }
    };
  }
  // Third user message: e.g. "I work from home, etc..."
  return {
    text: 'Here is an updated layout with a workspace. Anything else to add?',
    layout: {
      layoutId: 'Layout 2',
      rooms: [
        { id: 1, name: 'Bedroom', geometry: [[0,0],[0,40],[40,40],[40,0]], attributes: { program: 'bedroom', area: 16 } },
        { id: 2, name: 'Kitchen', geometry: [[50,0],[50,40],[90,40],[90,0]], attributes: { program: 'kitchen', area: 16 } },
        { id: 3, name: 'Living', geometry: [[0,50],[0,90],[90,90],[90,50]], attributes: { program: 'living', area: 36 } },
        { id: 4, name: 'Workspace', geometry: [[100,0],[100,30],[130,30],[130,0]], attributes: { program: 'workspace', area: 9 } }
      ]
    },
    parsedInput: {
      households: [
        { name: 'John', age: 34, relationship: 'self' },
        { name: 'Sarah', age: 32, relationship: 'partner' }
      ],
      activities: [
        { type: 'Cooking', time: 'often' },
        { type: 'Work', time: 'weekdays' }
      ],
      rooms: [
        { id: 1, name: 'Kitchen' , size: 'large' },
        { id: 2, name: 'Bedroom' , size: 'double'},
        { id: 3, name: 'Workspace' , size: 'medium'}
      ],
      brief: 'John and Sarah area a couple and cook a lot. They want one bedroom and a workspace.'
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
      // Force new object reference for reactivity
      agentState.value = agent.layout ? JSON.parse(JSON.stringify(agent.layout)) : null;
      parsedInput.value = agent.parsedInput ? JSON.parse(JSON.stringify(agent.parsedInput)) : null;
      console.log('App.vue setting agentState:', agent.layout);
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

