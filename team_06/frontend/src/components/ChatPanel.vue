<script setup>
import { ref } from 'vue'
import menuIcon from '../assets/menu.svg'
import sendIcon from '../assets/send.svg'
import searchIcon from '../assets/search.svg'
import ChatBox from './ChatBox.vue'
const search = ref('')
const count = ref(0)
</script>

<template>
  <section class="center-panel">
    <div class="center-panel-header-spacer">
        <span class="chat-title">AI Copilot</span>
    </div>
    <header class="chat-header">
      <button class="chat-history-btn" style="margin-right:8px;">
        <img :src="menuIcon" alt="Menu" width="20" height="20" />
      </button>
      <span class="chat-header-title">Chat History</span>
    </header>
    <div class="chat-search-bar">
      <input class="chat-search" type="text" placeholder="Search..." v-model="search" />
      <img class="chat-search-icon" :src="searchIcon" alt="Search" />
    </div>
    <ul v-if="search" class="chat-history-list">
      <li>Apartment for a young couple</li>
      <li>Daylight analysis</li>
    </ul>
    <div class="chat-area">
      <!-- Placeholder for chat messages -->
    </div>
    <footer class="chat-box-bar">
      <ChatBox />
    </footer>
  </section>
</template>

<style scoped>
.center-panel-header-spacer {
    margin-top: 96px;
    margin-bottom: 16px;
  width: 100%;
}
.center-panel {
  width: 420px;
  min-width: 420px;
  background: var(--color-white);
  display: flex;
  flex-direction: column;
  padding: 0;
}
.chat-title {
  font-size: var(--font-size-subtitle);
  font-weight: 600;
  color: var(--color-blue);
  padding: 28px 32px 28px 32px;
}
.chat-header {
  display: flex;
  align-items: center;
  padding: 28px 32px 0 32px;
  gap: 16px;
}

.chat-header-title {
  font-size: var(--font-size-bold);
  font-weight: 600;
  color: var(--color-text-primary);
  flex: 1;
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
  margin: 18px 32px 0 32px;
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
  margin: 0 32px;
}
.chat-box-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 32px 28px 32px;
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
</style>
