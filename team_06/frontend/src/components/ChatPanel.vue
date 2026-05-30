<script setup>
import { ref } from 'vue'
import menuIcon from '../assets/menu.svg'
const search = ref('')
const count = ref(0)
import imgIcon from '../assets/img.svg'
import codeIcon from '../assets/code.svg'
import micIcon from '../assets/mic.svg'
import sendIcon from '../assets/send.svg'
</script>

<template>
  <section class="center-panel">
    <header class="chat-header">
      <button class="chat-input-btn" style="margin-right:8px;">
        <img :src="menuIcon" alt="Menu" width="22" height="22" />
      </button>
      <span class="chat-header-title">Chat History</span>
      <input class="chat-search" type="text" placeholder="Search..." v-model="search" />
    </header>
    <ul v-if="search" class="chat-history-list">
      <li>Apartment for a young couple</li>
      <li>Daylight analysis</li>
    </ul>
    <div class="chat-area">
      <!-- Placeholder for chat messages -->
    </div>
    <footer class="chat-input-bar">
      <input class="chat-input" type="text" placeholder="What do you want to create next?" />
      <button class="chat-input-btn"><img :src="imgIcon" alt="Image" width="22" height="22" /></button>
      <button class="chat-input-btn"><img :src="codeIcon" alt="Code" width="22" height="22" /></button>
      <button class="chat-input-btn"><img :src="micIcon" alt="Mic" width="22" height="22" /></button>
      <button class="chat-input-btn"><img :src="sendIcon" alt="Send" width="22" height="22" /></button>
    </footer>
  </section>
</template>
