<template>
  <aside
    class="sidebar"
    :class="{ collapsed: app.sidebarCollapsed, 'is-compact': app.sidebarIsCompact }"
    @transitionend="app.onSidebarTransitionEnd"
  >
    <div class="sidebar-inner">
      <div class="brand">
        <span class="brand-icon">◆</span>
        <span class="brand-text sidebar-label">Agent Router</span>
      </div>

      <nav class="nav" aria-label="主导航">
        <router-link to="/" class="nav-item" active-class="active" exact-active-class="active">
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="7" height="7" rx="1" />
            <rect x="14" y="3" width="7" height="7" rx="1" />
            <rect x="14" y="14" width="7" height="7" rx="1" />
            <rect x="3" y="14" width="7" height="7" rx="1" />
          </svg>
          <span class="nav-text sidebar-label">仪表盘</span>
        </router-link>

        <ConfigNavList :items="app.orderedConfigNavItems" />
      </nav>

      <div class="footer">
        <button
          class="footer-btn theme-btn"
          :aria-label="themeLabel"
          :title="themeLabel"
          @click="cycleTheme"
        >
          <span class="theme-icon">{{ themeIcon }}</span>
          <span class="nav-text sidebar-label">{{ themeLabel }}</span>
        </button>
        <button
          class="footer-btn collapse-btn"
          :aria-label="app.sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'"
          :title="app.sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'"
          @click="app.toggleSidebar"
        >
          <svg
            class="collapse-icon"
            :class="{ 'is-collapsed': app.sidebarCollapsed }"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            aria-hidden="true"
          >
            <path d="M11 17l-5-5 5-5" />
          </svg>
        </button>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useAppStore } from "../stores/app";
import ConfigNavList from "./ConfigNavList.vue";

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
  --sidebar-ease: var(--transition-base);
  --sidebar-icon-size: 18px;
  --sidebar-hit-size: var(--button-height);
  position: fixed;
  left: 0;
  top: 0;
  bottom: 0;
  width: var(--sidebar-width);
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
  z-index: calc(var(--z-sticky) + 10);
  overflow: hidden;
  transition: width var(--sidebar-ease);
}
.sidebar.collapsed {
  width: var(--sidebar-collapsed-width);
}

.sidebar-inner {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.brand {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: var(--space-3);
  padding: var(--space-4);
  border-bottom: 1px solid var(--color-border);
  color: var(--color-text-default);
  font-size: var(--text-md);
  font-weight: var(--font-bold);
  flex-shrink: 0;
  transition:
    gap var(--sidebar-ease),
    padding var(--sidebar-ease),
    justify-content var(--sidebar-ease);
}
.sidebar.is-compact .brand {
  justify-content: center;
  gap: 0;
  height: var(--sidebar-hit-size);
  padding: 0;
}
.brand-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  min-width: 24px;
  color: var(--color-primary);
  font-size: 18px;
  line-height: 1;
  transition: width var(--sidebar-ease), height var(--sidebar-ease), min-width var(--sidebar-ease);
}
.sidebar.is-compact .brand-icon {
  width: var(--sidebar-icon-size);
  height: var(--sidebar-icon-size);
  min-width: var(--sidebar-icon-size);
  font-size: var(--sidebar-icon-size);
}
.brand-text {
  white-space: nowrap;
}

.nav {
  flex: 1;
  min-height: 0;
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--space-2);
  overflow-x: hidden;
  overflow-y: auto;
  transition:
    padding var(--sidebar-ease),
    align-items var(--sidebar-ease);
}
.sidebar.is-compact .nav {
  padding: var(--space-3) var(--space-2);
  align-items: center;
}

.nav-item {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: var(--space-3);
  width: 100%;
  padding: var(--space-3);
  color: var(--color-text-muted);
  text-decoration: none;
  border-radius: var(--radius-md);
  transition:
    width var(--sidebar-ease),
    gap var(--sidebar-ease),
    padding var(--sidebar-ease),
    background var(--transition-fast),
    color var(--transition-fast);
}
.sidebar.is-compact .nav-item {
  width: var(--sidebar-hit-size);
  height: var(--sidebar-hit-size);
  min-width: var(--sidebar-hit-size);
  justify-content: center;
  gap: 0;
  padding: 0;
  transition:
    background var(--transition-fast),
    color var(--transition-fast);
}
.nav-icon {
  width: var(--sidebar-icon-size);
  height: var(--sidebar-icon-size);
  min-width: var(--sidebar-icon-size);
  flex-shrink: 0;
}

.sidebar-label {
  overflow: hidden;
  white-space: nowrap;
  max-width: 8rem;
  opacity: 1;
  flex-shrink: 1;
}
.sidebar:not(.is-compact) :deep(.sidebar-label) {
  transition:
    max-width var(--sidebar-ease),
    opacity var(--sidebar-ease);
}
.sidebar.is-compact :deep(.sidebar-label) {
  max-width: 0;
  opacity: 0;
  visibility: hidden;
  margin: 0;
  padding: 0;
  transition: none;
}

.nav-item:hover {
  background: var(--color-surface-hover);
  color: var(--color-text-default);
}
.nav-item.active {
  background: var(--color-primary-muted);
  color: var(--color-primary);
}

.sidebar :deep(.nav-group) {
  margin-top: var(--space-2);
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  transition:
    margin-top var(--sidebar-ease),
    align-items var(--sidebar-ease);
}
.sidebar.is-compact :deep(.nav-group) {
  margin-top: 0;
  align-items: center;
}
.sidebar:not(.is-compact) :deep(.nav-group-label) {
  max-height: 1.5rem;
  opacity: 1;
  overflow: hidden;
  transition:
    max-height var(--sidebar-ease),
    opacity var(--sidebar-ease),
    padding var(--sidebar-ease),
    margin var(--sidebar-ease);
}
.sidebar.is-compact :deep(.nav-group-label) {
  max-height: 0;
  opacity: 0;
  padding: 0;
  margin: 0;
  transition: none;
}
.sidebar :deep(.nav-group-list) {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  transition: align-items var(--sidebar-ease);
}
.sidebar.is-compact :deep(.nav-group-list) {
  align-items: center;
}
.sidebar :deep(.nav-sub-item-wrap) {
  width: 100%;
  transition: width var(--sidebar-ease);
}
.sidebar.is-compact :deep(.nav-sub-item-wrap) {
  width: var(--sidebar-hit-size);
  height: var(--sidebar-hit-size);
}
.sidebar :deep(.nav-sub-item) {
  transition:
    width var(--sidebar-ease),
    height var(--sidebar-ease),
    gap var(--sidebar-ease),
    padding var(--sidebar-ease);
}
.sidebar.is-compact :deep(.nav-sub-item) {
  flex: 0 0 auto;
  width: var(--sidebar-hit-size);
  height: var(--sidebar-hit-size);
  justify-content: center;
  gap: 0;
  padding: 0;
  transition:
    background var(--transition-fast),
    color var(--transition-fast);
}
.sidebar.is-compact :deep(.nav-icon) {
  width: var(--sidebar-icon-size);
  height: var(--sidebar-icon-size);
  min-width: var(--sidebar-icon-size);
}

.footer {
  flex-shrink: 0;
  width: 100%;
  display: grid;
  grid-template-columns: minmax(0, 1fr) var(--button-height);
  grid-template-rows: var(--button-height);
  gap: var(--space-2);
  padding: var(--space-3);
  border-top: 1px solid var(--color-border);
  align-items: center;
}
.sidebar:not(.is-compact) .footer {
  transition:
    grid-template-columns var(--sidebar-ease),
    grid-template-rows var(--sidebar-ease),
    gap var(--sidebar-ease),
    padding var(--sidebar-ease);
}
.sidebar.is-compact .footer {
  grid-template-columns: 1fr;
  grid-template-rows: repeat(2, var(--sidebar-hit-size));
  gap: var(--space-1);
  padding: var(--space-2);
  justify-items: center;
  align-items: center;
  transition: none;
}
.footer-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--sidebar-hit-size);
  height: var(--sidebar-hit-size);
  padding: 0;
  background: transparent;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  border-radius: var(--radius-md);
  flex-shrink: 0;
  transition:
    background var(--transition-fast),
    color var(--transition-fast);
}
.sidebar:not(.is-compact) .theme-btn {
  width: auto;
  height: auto;
  min-width: 0;
  min-height: var(--sidebar-hit-size);
  padding: var(--space-2);
  justify-content: flex-start;
  gap: var(--space-2);
  transition:
    width var(--sidebar-ease),
    padding var(--sidebar-ease),
    gap var(--sidebar-ease),
    background var(--transition-fast),
    color var(--transition-fast);
}
.sidebar.is-compact .theme-btn {
  width: var(--sidebar-hit-size);
  height: var(--sidebar-hit-size);
  padding: 0;
  justify-content: center;
  gap: 0;
}
.sidebar.is-compact .theme-btn .sidebar-label {
  display: none;
}
.collapse-btn {
  width: var(--sidebar-hit-size);
  height: var(--sidebar-hit-size);
}
.footer-btn:hover {
  background: var(--color-surface-hover);
  color: var(--color-text-default);
}
.theme-icon {
  width: var(--sidebar-icon-size);
  height: var(--sidebar-icon-size);
  font-size: var(--sidebar-icon-size);
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.collapse-icon {
  display: block;
  width: var(--sidebar-icon-size);
  height: var(--sidebar-icon-size);
  flex-shrink: 0;
  transform-origin: center;
  transition: transform var(--sidebar-ease);
}
.collapse-icon.is-collapsed {
  transform: rotate(180deg);
}

.sidebar.is-compact :deep(.drag-handle) {
  display: none;
}
</style>
