<template>
  <div class="trend-section">
    <div class="trend-header">
      <div class="trend-tabs">
        <button
          v-for="d in daysOptions"
          :key="d"
          class="tab-btn"
          :class="{ active: days === d }"
          @click="$emit('update:days', d)"
        >
          近 {{ d }} 天
        </button>
      </div>
      <UiButton size="sm" variant="ghost" @click="exportPng">
        <template #icon>⬇</template>
        导出
      </UiButton>
    </div>
    <ChartPanel
      ref="chartPanelRef"
      title="调用趋势"
      :subtitle="`近 ${days} 天`"
      :option="option"
      :loading="loading"
      :empty="!loading && data.length === 0"
      empty-description="该时间范围内没有调用记录"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { EChartsOption } from "echarts";
import ChartPanel from "./ChartPanel.vue";
import UiButton from "./ui/UiButton.vue";
import type { DailyStat } from "../api";

const props = defineProps<{
  data: DailyStat[];
  days: number;
  loading?: boolean;
}>();

defineEmits<{
  (e: "update:days", days: number): void;
}>();

const daysOptions = [7, 30, 90];
const chartPanelRef = ref<InstanceType<typeof ChartPanel> | null>(null);

const option = computed<EChartsOption>(() => ({
  tooltip: { trigger: "axis" },
  legend: { data: ["调用总数", "成功", "费用"] },
  grid: { left: 50, right: 60, top: 30, bottom: 30 },
  xAxis: {
    type: "category",
    data: props.data.map((d) => d.day),
  },
  yAxis: [
    { type: "value", name: "次数" },
    { type: "value", name: "USD" },
  ],
  series: [
    {
      name: "调用总数",
      type: "bar",
      data: props.data.map((d) => d.count),
      itemStyle: { color: "#89b4fa" },
    },
    {
      name: "成功",
      type: "bar",
      data: props.data.map((d) => d.success_count),
      itemStyle: { color: "#a6e3a1" },
    },
    {
      name: "费用",
      type: "line",
      yAxisIndex: 1,
      data: props.data.map((d) => +(d.cost_usd || 0).toFixed(4)),
      itemStyle: { color: "#fab387" },
      lineStyle: { color: "#fab387" },
    },
  ],
}));

function exportPng() {
  const url = chartPanelRef.value?.exportImage();
  if (!url) return;
  const a = document.createElement("a");
  a.href = url;
  a.download = `trend-${props.days}d.png`;
  a.click();
}
</script>

<style scoped>
.trend-section {
  margin-bottom: var(--space-6);
}
.trend-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}
.trend-tabs {
  display: flex;
  gap: var(--space-1);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-1);
}
.tab-btn {
  background: transparent;
  border: none;
  color: var(--color-text-muted);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--text-sm);
  transition: all var(--transition-fast);
}
.tab-btn:hover {
  color: var(--color-text-default);
}
.tab-btn.active {
  background: var(--color-primary);
  color: var(--color-crust);
}
</style>
