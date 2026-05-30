<template>
  <div class="chatbox">
    <input class="chatbox-input" type="text" placeholder="What do you want to create next?" />
    <div class="chatbox-bottom-row">
      <div class="chatbox-btns">
        <button class="chatbox-btn"><img :src="imgIcon" alt="Image" width="24" height="24" /></button>
        <button class="chatbox-btn"><img :src="codeIcon" alt="Code" width="24" height="24" /></button>
        <button class="chatbox-btn"><img :src="micIcon" alt="Mic" width="24" height="24" /></button>
      </div>
      <button class="chatbox-send-btn"><img :src="sendIcon" alt="Send" width="20" height="20" /></button>
    </div>
  </div>
</template>

<script setup>
import imgIcon from '../assets/img.svg'
import codeIcon from '../assets/code.svg'
import micIcon from '../assets/mic.svg'
import sendIcon from '../assets/send.svg'
</script>

<style scoped>
.chatbox {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  background: var(--color-white);
  border-radius: var(--radius-card);
  box-shadow: 0 2px 8px rgba(33, 118, 255, 0.10);
  padding: 32px 32px 24px 32px;
  width: 100%;
  min-height: 120px;
  position: relative;
}
.chatbox-input {
  border: none;
  
  outline: none;
  background: transparent;
  font-size: var(--font-size-standard);
  color: #aaa;
  padding: 0;
  margin-bottom: 24px;
  width: 100%;
}
.chatbox-bottom-row {
  display: flex;
  flex-direction: row;
  align-items: flex-end;
  width: 100%;
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
  color: #888;
  font-size: 1.8rem;
  cursor: pointer;
  border-radius: 8px;
  transition: background 0.15s;
}
.chatbox-btn:focus {
  outline: none;
}
.chatbox-btn:hover {
  background: #f0f4fa;
  color: var(--color-blue);
}
.chatbox-send-btn {
  background: #e9f0fa;
  border: 2px solid #bbb;
  box-shadow: none;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  height: 32px;
  min-width: 48px;
  min-height: 48px;
  margin-left: auto;
  transition: background 0.15s, border 0.15s;
}
.chatbox-send-btn:hover {
  background: var(--color-blue);
  border: 2px solid var(--color-blue);
}
</style>
