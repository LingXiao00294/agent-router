<template>
  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-value">{{ summary.total_calls }}</div>
      <div class="stat-label">总调用数</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" :class="rateColor">{{ summary.success_rate }}%</div>
      <div class="stat-label">成功率</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">{{ formatTokens(summary.total_input_tokens + summary.total_output_tokens) }}</div>
      <div class="stat-label">总 Token</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${{ summary.total_cost_usd.toFixed(4) }}</div>
      <div class="stat-label">总费用 (USD)</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">{{ summary.avg_latency_ms }}ms</div>
      <div class="stat-label">平均延迟</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">{{ formatTokens(summary.total_cache_read) }}</div>
      <div class="stat-label">Cache 读取</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { Summary } from "../api";

const props = defineProps<{ summary: Summary }>();

const rateColor = computed(() =>
  props.summary.success_rate >= 99 ? "text-green" : props.summary.success_rate >= 90 ? "text-yellow" : "text-red"
);

function formatTokens(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}
</script>

<style scoped>
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}
.stat-card {
  background: #1e1e2e;
  border: 1px solid #313244;
  border-radius: 8px;
  padding: 16px;
  text-align: center;
}
.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #cdd6f4;
}
.stat-label {
  font-size: 13px;
  color: #a6adc8;
  margin-top: 4px;
}
.text-green { color: #a6e3a1; }
.text-yellow { color: #f9e2af; }
.text-red { color: #f38ba8; }
</style>
