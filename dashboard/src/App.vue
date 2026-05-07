<template>
  <div class="app">
    <Sidebar />
    <div class="main-area">
      <router-view />
    </div>
  </div>
</template>

<script setup lang="ts">
import Sidebar from "./components/Sidebar.vue";
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: #11111b;
  color: #cdd6f4;
}
.app { min-height: 100vh; display: flex; }
.main-area {
  margin-left: 200px;
  flex: 1;
  padding: 24px;
  max-width: calc(100vw - 200px);
}
</style>
