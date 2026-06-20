<template>
  <div class="app" :style="appStyle">
    <Sidebar />
    <main class="main-area">
      <router-view />
    </main>
    <ToastProvider />
    <UiConfirm />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from "vue";
import Sidebar from "./components/Sidebar.vue";
import ToastProvider from "./components/ui/ToastProvider.vue";
import UiConfirm from "./components/ui/UiConfirm.vue";
import { useAppStore } from "./stores/app";

const app = useAppStore();

const appStyle = computed(() => ({
  "--sidebar-current-width": app.sidebarCurrentWidth,
}));

onMounted(() => {
  document.body.classList.remove("nav-drag-active");
});
</script>

<style scoped>
.app {
  min-height: 100vh;
  display: flex;
}
.main-area {
  margin-left: var(--sidebar-current-width, var(--sidebar-width));
  flex: 1;
  padding: var(--space-5) var(--space-6);
  max-width: calc(100vw - var(--sidebar-current-width, var(--sidebar-width)));
  transition:
    margin-left var(--transition-base),
    max-width var(--transition-base);
}

@media (max-width: 768px) {
  .main-area {
    margin-left: var(--sidebar-collapsed-width);
    max-width: calc(100vw - var(--sidebar-collapsed-width));
    padding: var(--space-4);
  }
}
</style>
