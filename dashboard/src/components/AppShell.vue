<script setup lang="ts">
import { computed } from "vue";
import { useRoute, RouterLink } from "vue-router";
import { storeToRefs } from "pinia";
import { useAppStore } from "@/stores/app";
import { useConfigStore } from "@/stores/config";
import { useRefreshStore } from "@/stores/refresh";
import { useToast } from "@/composables/useToast";
import type { RouterMode } from "@/api/types";
import type { RefreshInterval } from "@/stores/refresh";

const app = useAppStore();
const configStore = useConfigStore();
const refresh = useRefreshStore();
const toast = useToast();
const route = useRoute();
const { healthy, mode, savingMode, config, staleData } = storeToRefs(app);
const { dirty } = storeToRefs(configStore);
const { interval } = storeToRefs(refresh);

const nav = [
  { to: "/", label: "Overview", name: "overview" },
  { to: "/calls", label: "Calls", name: "calls" },
  { to: "/config", label: "Config", prefix: "/config" },
];

function isActive(item: (typeof nav)[number]) {
  if ("prefix" in item && item.prefix) return route.path.startsWith(item.prefix);
  return route.path === item.to;
}

const healthLabel = computed(() => {
  if (healthy.value === null) return "检测中";
  return healthy.value ? "已连接" : "断开";
});

const modeDisabled = computed(
  () => !config.value || savingMode.value || dirty.value,
);

async function onModeChange(e: Event) {
  const next = (e.target as HTMLSelectElement).value as RouterMode;
  try {
    await app.setMode(next);
    toast.success(`路由模式已切换为 ${next}`);
  } catch (err) {
    toast.error(err instanceof Error ? err.message : "切换失败");
  }
}

function onInterval(e: Event) {
  const v = Number((e.target as HTMLSelectElement).value) as RefreshInterval;
  refresh.setIntervalSec(v);
}
</script>

<template>
  <div class="shell">
    <aside class="side">
      <div class="brand-block">
        <div class="brand">Agent Router</div>
        <p class="tagline">本地 LLM 路由监控</p>
      </div>
      <nav class="nav">
        <RouterLink
          v-for="item in nav"
          :key="item.to"
          :to="item.to"
          class="nav-link"
          :class="{ active: isActive(item) }"
        >
          {{ item.label }}
        </RouterLink>
      </nav>
      <div class="side-foot muted">
        <span class="mono">v0.2</span>
      </div>
    </aside>

    <div class="main">
      <header class="top">
        <div class="top-left">
          <span
            class="health"
            :class="healthy === true ? 'ok' : healthy === false ? 'bad' : ''"
          >
            <span class="dot" />
            {{ healthLabel }}
          </span>
          <span v-if="staleData" class="stale-badge badge badge-warn">数据可能过期</span>
        </div>
        <div class="top-actions">
          <label class="ctrl">
            <span class="ctrl-label">Mode</span>
            <select
              class="ctrl-select"
              :value="mode"
              :disabled="modeDisabled"
              :title="dirty ? '配置页有未保存更改' : undefined"
              @change="onModeChange"
            >
              <option value="failover">Failover</option>
              <option value="sticky">Sticky</option>
            </select>
          </label>
          <label class="ctrl">
            <span class="ctrl-label">Refresh</span>
            <select
              class="ctrl-select"
              :value="interval"
              @change="onInterval"
            >
              <option :value="0">Off</option>
              <option :value="5">5s</option>
              <option :value="10">10s</option>
              <option :value="30">30s</option>
              <option :value="60">60s</option>
            </select>
          </label>
          <button class="btn btn-sm" type="button" title="刷新 (R)" @click="refresh.bump()">
            刷新
          </button>
          <button class="btn btn-sm" type="button" @click="app.toggleTheme()">
            {{ app.theme === "light" ? "深色" : "浅色" }}
          </button>
        </div>
      </header>
      <main class="content">
        <slot />
      </main>
    </div>
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: var(--nav-width) 1fr;
  min-height: 100vh;
  min-height: 100dvh;
}

.side {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  padding: 1.25rem 1rem;
  border-right: 1px solid var(--border);
  background: color-mix(in srgb, var(--bg-elevated) 92%, transparent);
  position: sticky;
  top: 0;
  align-self: stretch;
  min-height: 100vh;
  min-height: 100dvh;
}

.brand {
  font-size: 1.15rem;
  font-weight: 700;
}

.tagline {
  margin: 0.25rem 0 0;
  font-size: 0.8rem;
  color: var(--text-muted);
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.nav-link {
  padding: 0.55rem 0.75rem;
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-weight: 600;
  transition: background 0.15s ease, color 0.15s ease;
}

.nav-link:hover {
  background: var(--bg-hover);
  color: var(--text);
}

.nav-link.active {
  background: var(--accent-soft);
  color: var(--accent);
}

.side-foot {
  margin-top: auto;
  font-size: 0.75rem;
}

.main {
  min-width: 0;
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
}

.content {
  flex: 1;
  padding: 1.25rem;
}

.top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  min-height: var(--header-height);
  padding: 0.65rem 1.25rem;
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--bg-elevated) 92%, transparent);
  position: sticky;
  top: 0;
  z-index: 10;
}

.top-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.top-left {
  display: flex;
  align-items: center;
  gap: 0.65rem;
}

.stale-badge {
  font-size: 0.72rem;
}

.health {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-muted);
}

.health .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-muted);
}

.health.ok {
  color: var(--success);
}
.health.ok .dot {
  background: var(--success);
  box-shadow: 0 0 0 3px var(--success-soft);
}

.health.bad {
  color: var(--danger);
}
.health.bad .dot {
  background: var(--danger);
}

.ctrl {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.8rem;
}

.ctrl-label {
  color: var(--text-muted);
  font-weight: 600;
}

.ctrl-select {
  min-height: 28px;
  padding: 0.15rem 0.4rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-elevated);
}

@media (max-width: 860px) {
  .shell {
    grid-template-columns: 1fr;
  }
  .side {
    position: relative;
    height: auto;
    border-right: none;
    border-bottom: 1px solid var(--border);
  }
  .nav {
    flex-direction: row;
    flex-wrap: wrap;
  }
}
</style>
