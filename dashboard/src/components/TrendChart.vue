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
import { useChartTheme } from "../composables/useChartTheme";
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
const { categoryAxis, valueAxis } = useChartTheme();

function formatDayLocal(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function fillDailyTrend(data: DailyStat[], days: number): DailyStat[] {
  const map = new Map(data.map((d) => [d.day.slice(0, 10), d]));
  const end = new Date();
  end.setHours(0, 0, 0, 0);
  const filled: DailyStat[] = [];

  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(end);
    d.setDate(d.getDate() - i);
    const key = formatDayLocal(d);
    const row = map.get(key);
    filled.push(
      row ?? {
        day: key,
        count: 0,
        success_count: 0,
        cost_usd: 0,
      }
    );
  }

  return filled;
}

const filledData = computed(() => fillDailyTrend(props.data, props.days));

const option = computed<EChartsOption>(() => {
  const rows = filledData.value;
  const labelInterval = rows.length > 14 ? Math.ceil(rows.length / 7) - 1 : 0;

  return {
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
    },
    legend: {
      data: ["调用总数", "成功", "费用"],
      top: 0,
    },
    grid: { left: 48, right: 52, top: 36, bottom: rows.length > 14 ? 48 : 32, containLabel: false },
    xAxis: {
      type: "category",
      data: rows.map((d) => d.day),
      ...categoryAxis.value,
      axisLabel: {
        ...categoryAxis.value.axisLabel,
        interval: labelInterval,
        rotate: rows.length > 14 ? 40 : 0,
        hideOverlap: true,
        formatter: (value: string) => value.slice(5),
      },
    },
    yAxis: [
      {
        type: "value",
        name: "次数",
        minInterval: 1,
        ...valueAxis.value,
      },
      {
        type: "value",
        name: "USD",
        ...valueAxis.value,
        splitLine: { show: false },
        axisLabel: {
          ...valueAxis.value.axisLabel,
          formatter: (v: number) => (v >= 1 ? v.toFixed(0) : v.toFixed(2)),
        },
      },
    ],
    series: [
      {
        name: "调用总数",
        type: "bar",
        data: rows.map((d) => d.count),
        barMaxWidth: 20,
        itemStyle: { color: "#89b4fa", borderRadius: [3, 3, 0, 0] },
      },
      {
        name: "成功",
        type: "bar",
        data: rows.map((d) => d.success_count),
        barMaxWidth: 20,
        itemStyle: { color: "#a6e3a1", borderRadius: [3, 3, 0, 0] },
      },
      {
        name: "费用",
        type: "line",
        yAxisIndex: 1,
        data: rows.map((d) => +(d.cost_usd || 0).toFixed(4)),
        smooth: true,
        showSymbol: rows.length <= 14,
        symbolSize: 6,
        itemStyle: { color: "#fab387" },
        lineStyle: { color: "#fab387", width: 2 },
      },
    ],
  };
});

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
