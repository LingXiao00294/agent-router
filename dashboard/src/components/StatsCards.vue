<template>
  <div class="stats-grid">
    <template v-if="loading">
      <UiCard v-for="i in 6" :key="i" class="stat-skeleton">
        <UiSkeleton variant="text" class="skeleton-value" />
        <UiSkeleton variant="text" class="skeleton-label" />
      </UiCard>
    </template>

    <template v-else-if="summary">
      <UiCard v-for="item in items" :key="item.label" class="stat-card" hoverable>
        <div class="stat-value" :class="item.color">{{ item.value }}</div>
        <div class="stat-label">{{ item.label }}</div>
      </UiCard>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { Summary } from "../api";
import UiCard from "./ui/UiCard.vue";
import UiSkeleton from "./ui/UiSkeleton.vue";

const props = defineProps<{
  summary: Summary | null;
  loading?: boolean;
}>();

const rateColor = computed(() => {
  if (!props.summary) return "";
  const rate = props.summary.success_rate;
  if (rate >= 99) return "success";
  if (rate >= 90) return "warning";
  return "danger";
});

function formatTokens(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

const items = computed(() => {
  if (!props.summary) return [];
  const s = props.summary;
  return [
    { label: "总调用数", value: String(s.total_calls), color: "" },
    { label: "成功率", value: s.success_rate.toFixed(2) + "%", color: rateColor.value },
    { label: "总 Token", value: formatTokens(s.total_input_tokens + s.total_output_tokens), color: "primary" },
    { label: "总费用 (USD)", value: "$" + s.total_cost_usd.toFixed(4), color: "" },
    { label: "平均延迟", value: s.avg_latency_ms + "ms", color: "" },
    { label: "Cache 读取", value: formatTokens(s.total_cache_read), color: "info" },
  ];
});
</script>

<style scoped>
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}
.stat-card {
  text-align: center;
}
.stat-value {
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--color-text-default);
  margin-bottom: var(--space-1);
}
.stat-value.success {
  color: var(--color-success);
}
.stat-value.warning {
  color: var(--color-warning);
}
.stat-value.danger {
  color: var(--color-danger);
}
.stat-value.primary {
  color: var(--color-primary);
}
.stat-value.info {
  color: var(--color-info);
}
.stat-label {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.stat-skeleton {
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.skeleton-value {
  width: 60%;
  margin: 0 auto;
  height: 32px;
}
.skeleton-label {
  width: 50%;
  margin: 0 auto;
  height: 16px;
}
</style>
