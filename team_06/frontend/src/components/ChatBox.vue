<template>
  <div class="chatbox">
    <input
      class="chatbox-input"
      type="text"
      v-model="inputMsg"
      @keyup.enter="sendMessage"
      placeholder="What do you want to create next?"
    />
    <div class="chatbox-bottom-row">
      <button v-if="inputMsg.trim()" class="chatbox-send-btn" @click="sendMessage">
        <img :src="sendWhiteIcon" alt="Send" width="16" height="16"  />
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import plusIcon from '../assets/icons/plus_simple.svg'
import sendWhiteIcon from '../assets/icons/send-white.svg'

const emit = defineEmits(['send'])
const inputMsg = ref('')

function sendMessage() {
  if (inputMsg.value.trim()) {
    emit('send', inputMsg.value)
    inputMsg.value = ''
  }
}
</script>

<style scoped>
.chatbox {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  background: var(--color-white);
  border-radius: var(--radius-card);
  border: 1px solid var(--color-border);
  padding: 12px 16px 8px 16px;
  width: 100%;
  position: relative;
  min-height: 100px;
  box-sizing: border-box;
}
.chatbox-input {
  border: none;
  outline: none;
  background: transparent;
  font-size: var(--font-size-standard);
  color: var(--color-text-secondary);
  padding: 8px;
  margin-bottom: 18px;
  width: 100%;
  min-height: 0;
  box-sizing: border-box;
}

.chatbox-btn:focus {
  outline: none;
}
.chatbox-send-btn {
  background:var(--color-blue);
  border: 0px;
  box-shadow: none;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  height: 32px;
  min-width: 38px;
  min-height: 38px;
  margin-left: auto;
  transition: background 0.15s, border 0.15s;
}
.chatbox-send-btn:hover {
  background: var(--color-marine);
}
</style>
