<script setup>
import { ref } from 'vue'
import menuIcon from '../assets/menu.svg'
import sendIcon from '../assets/send.svg'
import ChatBox from './ChatBox.vue'
const search = ref('')
const count = ref(0)
</script>

<template>
  <section class="center-panel">
    <div class="center-panel-header-spacer"></div>
    <header class="chat-header">
      <button class="chat-input-btn" style="margin-right:8px;">
        <img :src="menuIcon" alt="Menu" width="22" height="22" />
      </button>
      <span class="chat-header-title">Chat History</span>
    </header>
    <div class="chat-search-bar">
      <input class="chat-search" type="text" placeholder="Search..." v-model="search" />
    </div>
    <ul v-if="search" class="chat-history-list">
      <li>Apartment for a young couple</li>
      <li>Daylight analysis</li>
    </ul>
    <div class="chat-area">
      <!-- Placeholder for chat messages -->
    </div>
    <footer class="chat-input-bar">
      <ChatBox />
    </footer>
  </section>
</template>

<style scoped>
.center-panel-header-spacer {
  height: 64px;
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

.chat-header {
  display: flex;
  align-items: center;
  padding: 28px 32px 0 32px;
  gap: 16px;
}

.chat-header-title {
  font-size: 1.3rem;
  font-weight: 600;
  flex: 1;
}

.chat-search {
  flex: 2;
  max-width: 300px;
  border-radius: var(--radius);
  border: 1px solid var(--color-border);
  padding: 7px 14px;
  font-size: var(--font-size-standard);
  background: var(--color-grey-bg);
  outline: none;
}
.chat-search-bar {
  padding: 10px 32px 0 32px;
  background: var(--color-white);
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

.chat-input-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 32px 28px 32px;
  border-top: 1px solid var(--color-border);
  background: var(--color-white);
}

.chat-input {
  flex: 1;
  min-width: 180px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 10px 16px;
  font-size: var(--font-size-standard);
  outline: none;
  background: var(--color-grey-bg);
}

.chat-input-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0 6px;
  display: flex;
  align-items: center;
  color: var(--color-blue);
  font-size: 1.2rem;
}
.chat-search-bar {
  padding: 10px 32px 0 32px;
  background: var(--color-white);
}
</style>
