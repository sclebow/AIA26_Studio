
<script setup>
import { ref } from 'vue'
const isLeftPanelOpen = ref(true)
const isCenterPanelOpen = ref(true)
</script>

<template>
  <div class="flex h-screen font-sans">
    <!-- Left Sidebar (Constraints) -->
    <aside
      v-if="isLeftPanelOpen"
      class="w-[280px] h-full bg-cool-light-gray border-r border-canvas-border flex flex-col transition-all duration-200"
    >
      <div class="flex items-center justify-between p-4 border-b border-canvas-border">
        <span class="font-medium text-gray-700">Constraints</span>
        <button
          class="ml-2 p-1 rounded hover:bg-gray-200 transition-all"
          @click="isLeftPanelOpen = false"
        >
          <span class="material-icons">chevron_left</span>
        </button>
      </div>
      <div class="flex-1 p-4">
        <!-- Sidebar content here -->
      </div>
    </aside>
    <!-- Left Sidebar Toggle -->
    <button
      v-else
      class="absolute left-0 top-4 z-10 bg-cool-light-gray border border-canvas-border rounded-r px-2 py-1 shadow hover:brightness-110 transition-all duration-200"
      @click="isLeftPanelOpen = true"
    >
      <span class="material-icons">chevron_right</span>
    </button>

    <!-- Center Sidebar (AI Chat) -->
    <aside
      v-if="isCenterPanelOpen"
      class="w-[320px] h-full bg-white border-r border-canvas-border flex flex-col transition-all duration-200"
    >
      <div class="flex items-center justify-between p-4 border-b border-canvas-border">
        <span class="font-medium text-gray-700">AI Chat</span>
        <button
          class="ml-2 p-1 rounded hover:bg-gray-100 transition-all"
          @click="isCenterPanelOpen = false"
        >
          <span class="material-icons">chevron_left</span>
        </button>
      </div>
      <div class="flex-1 p-4">
        <!-- Chat content here -->
      </div>
    </aside>
    <!-- Center Sidebar Toggle -->
    <button
      v-else
      class="absolute left-[280px] top-4 z-10 bg-white border border-canvas-border rounded-r px-2 py-1 shadow hover:brightness-110 transition-all duration-200"
      @click="isCenterPanelOpen = true"
    >
      <span class="material-icons">chevron_right</span>
    </button>

    <!-- Main Canvas Area -->
    <main class="flex-1 h-full bg-cool-light-gray flex flex-col items-center justify-center relative">
      <div class="absolute top-4 right-4 flex gap-2">
        <!-- Example Gradient Button -->
        <button
          class="bg-gradient-to-r from-sky-500 to-sky-600 text-white font-semibold px-6 py-2 rounded shadow-md hover:brightness-110 transition-all duration-200 active:scale-95"
        >
          Primary Action
        </button>
      </div>
      <div class="w-[600px] max-w-full bg-white shadow-md rounded-lg p-8 flex flex-col items-center">
        <h1 class="text-2xl font-bold mb-4">InHabit Canvas</h1>
        <p class="text-gray-500 mb-2">This is the main canvas area. Floating cards and elements appear here.</p>
        <!-- Example floating card -->
        <div class="bg-white shadow-md rounded p-4 mt-4 w-full">
          <span class="font-medium text-gray-700">Floating Card Example</span>
        </div>
      </div>
    </main>
  </div>
</template>
