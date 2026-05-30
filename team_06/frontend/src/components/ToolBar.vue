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
.toolbar-save-row {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 18px;
  justify-content: flex-end;
  margin: 16px 32px 16px 0;
}
.toolbar-inline {
  margin: 0;
}

.toolbar-inline {
  margin: 0;
}
.toolbar-save-group {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}
.toolbar-card {
  background: var(--color-white);
  border-radius: var(--radius);
  box-shadow: var(--shadow-card);
  margin: 16px auto 16px auto;
  padding: 10px 18px;
  display: flex;
  justify-content: center;
  align-items: center;
  width: fit-content;
  min-width: 0;
}
.layout-input-btn {
  background: none !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 6px;
  display: flex;
  align-items: center;
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
