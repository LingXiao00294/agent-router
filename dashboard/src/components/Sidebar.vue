<template>
  <aside class="sidebar" :class="{ collapsed: app.sidebarCollapsed }">
    <div class="brand">
      <span class="brand-icon">◆</span>
      <span class="brand-text">Agent Router</span>
    </div>

    <nav class="nav" aria-label="主导航">
      <router-link to="/" class="nav-item" active-class="active">
        <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="3" width="7" height="7" rx="1" />
          <rect x="14" y="3" width="7" height="7" rx="1" />
          <rect x="14" y="14" width="7" height="7" rx="1" />
          <rect x="3" y="14" width="7" height="7" rx="1" />
        </svg>
        <span class="nav-text">仪表盘</span>
      </router-link>
      <router-link to="/config" class="nav-item" active-class="active">
        <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
        <span class="nav-text">配置管理</span>
      </router-link>
    </nav>

    <div class="footer">
      <button
        class="theme-btn"
        :aria-label="themeLabel"
        :title="themeLabel"
        @click="cycleTheme"
      >
        <span class="theme-icon">{{ themeIcon }}</span>
        <span class="nav-text">{{ themeLabel }}</span>
      </button>
      <button
        class="collapse-btn"
        :aria-label="app.sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'"
        @click="app.toggleSidebar"
      >
        <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M11 17l-5-5 5-5" />
          <path d="M18 17l-5-5 5-5" v-if="app.sidebarCollapsed" />
        </svg>
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useAppStore } from "../stores/app";

const app = useAppStore();

const themeIcon = computed(() => {
  if (app.themeMode === "light") return "☀";
  if (app.themeMode === "dark") return "☾";
  return "◐";
});

const themeLabel = computed(() => {
  if (app.themeMode === "light") return "亮色";
  if (app.themeMode === "dark") return "暗色";
  return "跟随系统";
});

function cycleTheme() {
  const order: Array<"dark" | "light" | "system"> = ["dark", "light", "system"];
  const idx = order.indexOf(app.themeMode);
  app.setTheme(order[(idx + 1) % order.length]);
}
</script>

<style scoped>
.sidebar {
  position: fixed;
  left: 0;
  top: 0;
  bottom: 0;
  width: var(--sidebar-width);
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  z-index: var(--z-sticky);
  transition: width var(--transition-base);
}
.sidebar.collapsed {
  width: var(--sidebar-collapsed-width);
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-4) var(--space-4);
  border-bottom: 1px solid var(--color-border);
  color: var(--color-text-default);
  font-size: var(--text-md);
  font-weight: var(--font-bold);
  overflow: hidden;
}
.brand-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  min-width: 24px;
  color: var(--color-primary);
}
.brand-text {
  white-space: nowrap;
}
.sidebar.collapsed .brand-text,
.sidebar.collapsed .nav-text {
  opacity: 0;
  width: 0;
  overflow: hidden;
}

.nav {
  flex: 1;
  padding: var(--space-3) var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-3);
  color: var(--color-text-muted);
  text-decoration: none;
  border-radius: var(--radius-md);
  transition: all var(--transition-fast);
}
.nav-item:hover {
  background: var(--color-surface-hover);
  color: var(--color-text-default);
}
.nav-item.active {
  background: var(--color-primary-muted);
  color: var(--color-primary);
}
.nav-icon {
  width: 18px;
  height: 18px;
  min-width: 18px;
}
.nav-text {
  white-space: nowrap;
  transition: opacity var(--transition-fast);
}

.footer {
  padding: var(--space-3);
  border-top: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}
.theme-btn,
.collapse-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  background: transparent;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  padding: var(--space-2);
  border-radius: var(--radius-md);
}
.theme-btn:hover,
.collapse-btn:hover {
  background: var(--color-surface-hover);
  color: var(--color-text-default);
}
.theme-icon {
  width: 18px;
  text-align: center;
}
</style>
