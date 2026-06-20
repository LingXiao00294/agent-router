<template>
  <div class="config-layout">
    <div class="config-save-bar">
      <UiButton
        variant="primary"
        :loading="configStore.saving"
        :disabled="!configStore.isDirty"
        @click="save"
      >
        保存配置
      </UiButton>
    </div>

    <PageHeader :title="pageTitle" :subtitle="pageSubtitle" class="config-page-header" />

    <UiErrorBanner
      v-if="configStore.error"
      :message="configStore.error"
      retry
      class="global-error"
      @retry="configStore.loadConfig"
    />

    <div v-if="configStore.loading" class="loading-wrap">
      <UiSpinner size="lg" />
      <p class="text-muted">加载配置中...</p>
    </div>

    <router-view v-else />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted } from "vue";
import { onBeforeRouteLeave, useRoute } from "vue-router";
import { useConfigStore } from "../../stores/config";
import { useConfirm } from "../../composables/useConfirm";
import { useToast } from "../../composables/useToast";
import PageHeader from "../../components/PageHeader.vue";
import UiButton from "../../components/ui/UiButton.vue";
import UiSpinner from "../../components/ui/UiSpinner.vue";
import UiErrorBanner from "../../components/ui/UiErrorBanner.vue";

const route = useRoute();
const configStore = useConfigStore();
const { confirm } = useConfirm();
const toast = useToast();

const pageTitle = computed(() => String(route.meta.title ?? "配置管理"));
const pageSubtitle = computed(() => {
  const subtitle = route.meta.subtitle;
  return subtitle ? String(subtitle) : undefined;
});

async function save() {
  if (!configStore.isDirty || configStore.saving) return;
  try {
    const ok = await configStore.saveConfig();
    if (ok) {
      toast.success("配置已保存并热重载");
    }
  } catch {
    toast.error(configStore.error || "保存失败");
  }
}

function onKeydown(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    save();
  }
}

onBeforeRouteLeave(async (to, _from, next) => {
  if (to.path.startsWith("/config")) return next();
  if (!configStore.isDirty) return next();
  const ok = await confirm({
    title: "未保存的更改",
    message: "配置已修改但未保存，确定离开吗？",
    confirmText: "离开",
    cancelText: "留下",
  });
  next(ok);
});

onMounted(() => {
  configStore.loadConfig();
  document.addEventListener("keydown", onKeydown);
});

onUnmounted(() => {
  document.removeEventListener("keydown", onKeydown);
});
</script>

<style scoped>
.config-layout {
  padding: 0 var(--space-1);
  padding-top: var(--space-1);
}
.config-layout :deep(.config-page-header) {
  padding-right: 7rem;
}
.config-save-bar {
  position: fixed;
  top: var(--space-4);
  right: var(--space-6);
  z-index: calc(var(--z-sticky) + 1);
}
.global-error {
  margin-bottom: var(--space-4);
}
.loading-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-8) 0;
  color: var(--color-text-muted);
}
</style>
