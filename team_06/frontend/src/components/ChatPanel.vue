<script setup>
import { ref, watch, nextTick } from 'vue'
import menuIcon from '../assets/icons/menu.svg'
import sendIcon from '../assets/icons/send.svg'
import searchIcon from '../assets/icons/search.svg'
import userIcon from '../assets/icons/user.svg'
import chevronIcon from '../assets/icons/chevron.svg'
import ChatBox from './ChatBox.vue'
const search = ref('')


const props = defineProps({
  chat: {
    type: Array,
    default: () => []
  },
  index: {
    type: Number,
    default: 0
  }
})
const emit = defineEmits(['send'])

const chatArea = ref(null)


// Auto-scroll to bottom when chat updates
watch(() => props.chat.length, () => {
  nextTick(() => {
    if (chatArea.value) chatArea.value.scrollTop = chatArea.value.scrollHeight
  })
})
</script>

<template>
  <section class="chat-panel">
    <header class="chat-header">
      <div class="chat-header-avatar">
        <img :src="userIcon" alt="User" width="32" height="32" style="border-radius:50%;background:#e0e3ea;" />
        <img :src="chevronIcon" alt="Chevron" width="18" height="18" />
      </div>
    </header>
    <div class="chat-title">AI Copilot</div>
    <section class="chat-history">
      <div class="chat-history-title">
        <img :src="menuIcon" alt="Chat History" width="20" height="20" />
        Chat History
      </div>
    </section>
    <div class="chat-search-bar">
      <input class="chat-search" type="text" placeholder="Search..." v-model="search" />
      <img class="chat-search-icon" :src="searchIcon" alt="Search" />
    </div>
    <ul v-if="search" class="chat-history-list">
      <li>Apartment for a young couple</li>
      <li>Daylight analysis</li>
    </ul>
    <div class="chat-area" ref="chatArea" style="overflow-y:auto;">
      <div v-for="msg in chat" :key="msg.id" :class="['chat-msg', msg.role]">
        <span>{{ msg.text }}</span>
      </div>
    </div>
    <footer class="chat-box-bar">
      <ChatBox @send="msg => emit('send', msg)" />
    </footer>
  </section>
</template>

<style scoped>
.chat-header {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  padding: 28px 32px 0 0;
  gap: 0;
  position: relative;
}
.chat-header-avatar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.chat-panel {
  width: 400px;
  min-width: 400px;
  background: var(--color-white);
  border-left: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  padding: 0;
}
.chat-title {
  font-size: var(--font-size-subtitle);
  color: var(--color-blue);
  padding: 28px 32px 28px 32px;
}
.chat-history {
  margin-bottom: 12px;
}
.chat-history-title {
  display: flex;
  align-items: center;
  font-size: var(--font-size-bold);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-primary);
  gap: 8px;
  margin-left: 32px;
  margin-top: 12px;
}
.chat-search {
  display: flex;
  font-size: var(--font-size-standard);
  color: var(--color-text-secondary);
  flex-direction: column;
  align-items: stretch;
  background: var(--color-white);
  border-radius: var(--radius-card);
  padding: 12px 12px;
  width: 100%;
  position: relative;
  border: 1px solid var(--color-border);
}
.chat-search-bar {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 32px 28px 32px;
}
.chat-search {
  width: 100%;
  padding-right: 36px;
}
.chat-search-icon {
  position: absolute;
  right: 44px;
  width: 20px;
  height: 20px;
  pointer-events: none;
  opacity: 0.7;
}
.chat-history-list {
  margin: 18px 28px 0 28px;
  padding: 0;
  list-style: none;
  color: var(--color-text-secondary);
  font-size: var(--font-size-standard);
  flex: 0 0 auto;
}
.chat-area {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  margin: 0 28px;
}
.chat-box-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 28px 28px 28px;
  background: var(--color-white);
}
.chat-history-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0 6px;
  display: flex;
  align-items: center;
  color: var(--color-blue);
  font-size: 1.2rem;
}
.chat-msg {
  max-width: 75%;
  margin: 6px 0;
  padding: 10px 16px;
  border-radius: 16px;
  font-size: var(--font-size-standard);
  word-break: break-word;
  display: inline-block;
}
.chat-msg.user {
  align-self: flex-end;
  background: var(--color-light-blue);
  color: var(--color-text-primary);
  border: 1.5px solid var(--color-blue);
  margin-left: auto;
  margin-right: 0;
  text-align: right;
}
.chat-msg.agent {
  align-self: flex-start;
  background: transparent;
  color: var(--color-text-primary);
  border: none;
  margin-right: auto;
  margin-left: 0;
  text-align: left;
  padding: 0;
  font-size: var(--font-size-standard);
  box-shadow: none;
}
</style>
