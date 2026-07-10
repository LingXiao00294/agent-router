<script setup lang="ts">
import { onMounted, onUnmounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { storeToRefs } from "pinia";
import AppShell from "@/components/AppShell.vue";
import ToastStack from "@/components/ToastStack.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import { provideToast } from "@/composables/useToast";
import { provideConfirm } from "@/composables/useConfirm";
import { useAppStore } from "@/stores/app";
import { useMetricsStore } from "@/stores/metrics";
import { useCallsStore } from "@/stores/calls";
import { useConfigStore } from "@/stores/config";
import { useRefreshStore } from "@/stores/refresh";

const toast = provideToast();
provideConfirm();

const app = useAppStore();
const metrics = useMetricsStore();
const calls = useCallsStore();
const config = useConfigStore();
const refresh = useRefreshStore();
const route = useRoute();
const router = useRouter();
const { tick } = storeToRefs(refresh);

async function bootstrap() {
  app.initTheme();
  await Promise.all([
    app.checkHealth(),
    app.loadConfig(true),
    app.loadCircuit(true),
  ]);
}

async function silentRefresh() {
  let failed = false;
  try {
    await Promise.all([
      app.checkHealth(),
      app.loadCircuit(true),
    ]);
  } catch {
    failed = true;
  }
  try {
    if (route.name === "overview") {
      await metrics.refresh(true);
    } else if (route.name === "calls") {
      const q = route.query;
      await calls.fetchList(
        {
          page: Number(q.page || 1),
          size: Number(q.size || 50),
          model: typeof q.model === "string" ? q.model : undefined,
          status: typeof q.status === "string" ? q.status : undefined,
        },
        true,
      );
    }
  } catch {
    failed = true;
  }

  if (metrics.error || calls.error || app.healthy === false) {
    failed = true;
  }

  if (failed) {
    if (!app.staleData) {
      toast.error("自动刷新失败，数据可能过期");
    }
    app.staleData = true;
  } else {
    app.staleData = false;
  }
}

watch(tick, () => {
  void silentRefresh();
});

function onKey(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement)?.tagName;
  const typing =
    tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" ||
    (e.target as HTMLElement)?.isContentEditable;

  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
    if (route.path.startsWith("/config") && config.dirty) {
      e.preventDefault();
      void config
        .save()
        .then(async () => {
          await app.loadConfig(true);
          toast.success("配置已保存并热重载");
        })
        .catch((err: Error) => toast.error(err.message));
    }
    return;
  }

  if (!typing && e.key.toLowerCase() === "r" && !e.ctrlKey && !e.metaKey) {
    e.preventDefault();
    refresh.bump();
  }
}

onMounted(() => {
  void bootstrap();
  window.addEventListener("keydown", onKey);
});

onUnmounted(() => {
  window.removeEventListener("keydown", onKey);
});

router.beforeEach(async (to, from) => {
  if (
    from.path.startsWith("/config") &&
    !to.path.startsWith("/config") &&
    config.dirty
  ) {
    const ok = window.confirm("配置有未保存更改，确定离开？");
    if (!ok) return false;
  }
  return true;
});
</script>

<template>
  <AppShell>
    <RouterView />
  </AppShell>
  <ToastStack />
  <ConfirmDialog />
</template>
