<script setup>
import userIcon from '../assets/user.svg'
import chevronIcon from '../assets/chevron.svg'
import uploadIcon from '../assets/upload.svg'
import editIcon from '../assets/edit.svg'
import rotateIcon from '../assets/rotate.svg'
import downloadIcon from '../assets/download.svg'
</script>

<template>
  <aside class="right-panel">
    <header class="right-header">
      <div class="right-header-avatar">
        <img :src="userIcon" alt="User" width="32" height="32" style="border-radius:50%;background:#e0e3ea;" />
        <img :src="chevronIcon" alt="Chevron" width="18" height="18" />
      </div>
      <button class="save-layout-btn right">Save Layout</button>
    </header>
    <div class="toolbar-card">
      <div class="toolbar">
        <button class="chat-input-btn"><img :src="uploadIcon" alt="Upload" width="22" height="22" /></button>
        <button class="chat-input-btn"><img :src="editIcon" alt="Edit" width="22" height="22" /></button>
        <button class="chat-input-btn"><img :src="rotateIcon" alt="Rotate" width="22" height="22" /></button>
        <button class="chat-input-btn"><img :src="downloadIcon" alt="Download" width="22" height="22" /></button>
      </div>
    </div>
    <div class="canvas-area">
      <div class="canvas">Canvas Area</div>
    </div>
    <div class="layout-summary-card">
      <div class="layout-summary-title">Layout-001</div>
      <div class="layout-summary-area">52<span style="font-size:1.1rem;font-weight:400;">sqm</span></div>
      <ul class="layout-summary-list">
        <li>Bedroom - 16 sqm</li>
        <li>Bathroom - 5 sqm</li>
        <li>Foyer - 2 sqm</li>
        <li>Living - 20 sqm</li>
        <li>Kitchen - 9 sqm</li>
      </ul>
      <div class="layout-summary-issues">
        <div class="layout-summary-issues-title">Issues</div>
        <ul class="layout-summary-issues-list">
          <li>Lack of daylight</li>
          <li>Outline too small</li>
        </ul>
      </div>
    </div>
  </aside>
</template>
