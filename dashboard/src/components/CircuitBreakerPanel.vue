<template>
  <UiCard
    title="熔断状态"
    :subtitle="Object.keys(states).length ? `${Object.keys(states).length} 个 provider` : ''"
    class="cb-panel"
  >
    <UiErrorBanner v-if="error" :message="error" retry @retry="$emit('refresh')" />

    <div v-if="loading" class="cb-skeleton">
      <UiSkeleton v-for="i in 3" :key="i" variant="rect" class="cb-skeleton-row" />
    </div>

    <UiEmpty
      v-else-if="Object.keys(states).length === 0"
      title="暂无熔断记录"
      description="所有 provider 运行正常"
      icon="✓"
    />

    <div v-else class="cb-list">
      <div v-for="(state, name) in states" :key="name" class="cb-row">
        <span class="cb-name">{{ name }}</span>
        <UiBadge :variant="variantFor(state)" size="sm">{{ labelFor(state) }}</UiBadge>
        <UiButton
          v-if="state !== 'closed'"
          size="sm"
          variant="secondary"
          :loading="resetting === name"
          @click="$emit('reset', name)"
        >
          重置
        </UiButton>
      </div>
    </div>

    <template #footer>
      <UiButton size="sm" variant="ghost" :loading="loading" @click="$emit('refresh')">
        刷新状态
      </UiButton>
    </template>
  </UiCard>
</template>

<script setup lang="ts">
import UiCard from "./ui/UiCard.vue";
import UiBadge from "./ui/UiBadge.vue";
import UiButton from "./ui/UiButton.vue";
import UiSkeleton from "./ui/UiSkeleton.vue";
import UiEmpty from "./ui/UiEmpty.vue";
import UiErrorBanner from "./ui/UiErrorBanner.vue";

defineProps<{
  states: Record<string, string>;
  loading?: boolean;
  error?: string | null;
  resetting?: string | null;
}>();

defineEmits<{
  refresh: [];
  reset: [provider: string];
}>();

const labels: Record<string, string> = {
  closed: "正常",
  open: "已熔断",
  half_open: "半开",
};

function labelFor(state: string): string {
  return labels[state] || state;
}

function variantFor(state: string): "success" | "warning" | "error" | "neutral" {
  if (state === "closed") return "success";
  if (state === "half_open") return "warning";
  if (state === "open") return "error";
  return "neutral";
}
</script>

<style scoped>
.cb-panel {
  margin-bottom: var(--space-6);
}
.cb-skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.cb-skeleton-row {
  height: 40px;
  border-radius: var(--radius-md);
}
.cb-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.cb-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--color-surface-elevated);
  border-radius: var(--radius-md);
}
.cb-name {
  flex: 1;
  font-size: var(--text-base);
  color: var(--color-text-default);
}
</style>
