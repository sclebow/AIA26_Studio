<template>
  <div class="toolbar">
    <button class="layout-input-btn"><img :src="uploadIcon" alt="Upload" width="22" height="22" /></button>
    <button class="layout-input-btn"><img :src="editIcon" alt="Edit" width="22" height="22" /></button>
    <button class="layout-input-btn"><img :src="rotateIcon" alt="Rotate" width="22" height="22" /></button>
    <button class="layout-input-btn"><img :src="downloadIcon" alt="Download" width="22" height="22" /></button>
  </div>
</template>

<script setup>
import uploadIcon from '../assets/upload.svg'
import editIcon from '../assets/edit.svg'
import rotateIcon from '../assets/rotate.svg'
import downloadIcon from '../assets/download.svg'
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 18px;
  margin: 0;
}
.layout-input-btn {
  background: none !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 6px;
  display: flex;
  align-items: center;
  font-size: 1.2rem;
  cursor: pointer;
  transition: background 0.15s;
}
.layout-input-btn:focus {
  outline: none;
}
.layout-input-btn:hover {
  background: none;
  box-shadow: none;
}


</style>
