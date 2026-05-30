
<template>
	<div id="app">
		<div class="app-layout">
			<NavTab :tab="tab" @change="tab = $event" />
			<Sidebar :tab="tab" />
			<ChatPanel />
			<RightPanel />
		</div>
	</div>
</template>

<script setup>
import { ref } from 'vue'
import NavTab from './components/NavTab.vue'
import Sidebar from './components/Sidebar.vue'
import ChatPanel from './components/ChatPanel.vue'
import RightPanel from './components/RightPanel.vue'

const tab = ref('create')
</script>

<style src="./style.css"></style>

