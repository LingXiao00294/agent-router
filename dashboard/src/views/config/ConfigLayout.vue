<script setup lang="ts">
import { onMounted } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { storeToRefs } from "pinia";
import { useAppStore } from "@/stores/app";
import { useConfigStore } from "@/stores/config";
import { useConfirm } from "@/composables/useConfirm";
import { useToast } from "@/composables/useToast";

const store = useConfigStore();
const app = useAppStore();
const toast = useToast();
const confirm = useConfirm();
const route = useRoute();
const { dirty, saving, loading, error } = storeToRefs(store);

const links = [
  { to: "/config/models", label: "Models" },
  { to: "/config/providers", label: "Providers" },
  { to: "/config/server", label: "Server" },
  { to: "/config/router", label: "Router" },
  { to: "/config/circuit", label: "Circuit" },
];

onMounted(() => {
  void store
    .load()
    .then(() => app.loadConfig(true))
    .catch((err: Error) => toast.error(err.message));
});

async function save() {
  try {
    await store.save();
    await app.loadConfig(true);
    toast.success("配置已更新并热重载");
  } catch (err) {
    toast.error(err instanceof Error ? err.message : "保存失败");
  }
}

async function reload() {
  if (dirty.value) {
    const ok = await confirm.confirm({
      title: "放弃未保存更改？",
      message: "重载将丢弃当前编辑，恢复为磁盘上的配置。",
      confirmText: "重载",
      danger: true,
    });
    if (!ok) return;
  }
  try {
    await store.load();
    await app.loadConfig(true);
    toast.success("已从磁盘重载配置");
  } catch (err) {
    toast.error(err instanceof Error ? err.message : "重载失败");
  }
}
</script>

<template>
  <div class="page fade-up">
    <header class="page-head">
      <div>
        <h1>Config</h1>
        <p class="muted">编辑 config.toml 并热重载 · Ctrl/Cmd+S 保存</p>
      </div>
      <div class="actions">
        <span v-if="dirty" class="badge badge-warn">未保存</span>
        <button class="btn" type="button" :disabled="loading" @click="reload">重载</button>
        <button
          class="btn btn-primary"
          type="button"
          :disabled="!dirty || saving"
          @click="save"
        >
          {{ saving ? "保存中…" : "保存" }}
        </button>
      </div>
    </header>

    <div v-if="error" class="error-state panel">{{ error }}</div>
    <div v-else-if="loading && !store.draft" class="empty-state panel">加载配置…</div>
    <template v-else>
      <nav class="subnav">
        <RouterLink
          v-for="l in links"
          :key="l.to"
          :to="l.to"
          class="sub-link"
          :class="{ active: route.path === l.to }"
        >
          {{ l.label }}
        </RouterLink>
      </nav>
      <RouterView />
    </template>
  </div>
</template>

<style scoped>
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1rem;
}
.page-head h1 {
  margin: 0;
  font-size: 1.5rem;
}
.page-head p {
  margin: 0.25rem 0 0;
}
.actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.subnav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-bottom: 1rem;
}
.sub-link {
  padding: 0.4rem 0.75rem;
  border-radius: 999px;
  border: 1px solid var(--border);
  font-weight: 600;
  font-size: 0.85rem;
  color: var(--text-secondary);
}
.sub-link.active {
  background: var(--accent-soft);
  border-color: transparent;
  color: var(--accent);
}
</style>
