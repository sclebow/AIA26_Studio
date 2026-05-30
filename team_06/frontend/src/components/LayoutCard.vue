<template>  
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
</template>

<style scoped>
.layout-summary-card {
  background: var(--color-white);
  border-radius: var(--radius-card);
  border: 1px solid var(--color-border);
  font-size: var(--font-size-standard);
  color: var(--color-text);
  min-width: 180px;
}
.layout-summary-title {
  font-size: var(--font-size-bold);
  font-weight: 700;
  color: var(--color-blue);
  margin-bottom: 8px;
}
.layout-summary-area {
  font-size: var(--font-size-title);
  font-weight: 700;
  margin-bottom: 12px;
  color: var(--color-text-secondary);
}
.layout-summary-list {
  margin: 0 0 12px 0;
  padding: 0;
  list-style: none;
  color: var(--color-text-primary);
}
.layout-summary-issues {
  margin-top: 10px;
}
.layout-summary-issues-title {
  font-weight: 600;
  color: var(--color-text-error);
  margin-bottom: 4px;
}
.layout-summary-issues-list {
  margin: 0;
  padding: 0 0 0 16px;
  color: var(--color-text-error);
  font-size: var(--font-size-bold);
}
.layout-summary-card {
    margin: 16px;
    padding: 32px 32px;
}
</style>