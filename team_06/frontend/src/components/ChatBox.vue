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
      <div class="chatbox-btns">
        <button class="chatbox-btn"><img :src="imgIcon" alt="Image" width="20" height="20" /></button>
        <button class="chatbox-btn"><img :src="codeIcon" alt="Code" width="20" height="20" /></button>
        <button class="chatbox-btn"><img :src="micIcon" alt="Mic" width="20" height="20" /></button>
      </div>
      <button class="chatbox-send-btn" @click="sendMessage" :disabled="!inputMsg.trim()">
        <img :src="sendWhiteIcon" alt="Send" width="16" height="16" />
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import imgIcon from '../assets/icons/img.svg'
import codeIcon from '../assets/icons/code.svg'
import micIcon from '../assets/icons/mic.svg'
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

  min-height: 120px;
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
.chatbox-bottom-row {
  display: flex;
  flex-direction: row;
  align-items: flex-end;
  padding: 8px;
  width: 100%;
  margin-bottom: 0;
}
.chatbox-btns {
  display: flex;
  align-items: flex-end;
  gap: 32px;
}
.chatbox-btn {
  background: none;
  border: none;
  box-shadow: none;
  margin-bottom: 12px;
  padding: 0;
  display: flex;
  align-items: center;
  color: var(--color-text-secondary);
  font-size: 1.8rem;
  cursor: pointer;
  border-radius: 8px;
  transition: background 0.15s;
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
