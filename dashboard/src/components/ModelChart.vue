<template>
  <div class="model-charts-row">
    <ChartPanel
      title="模型分布"
      subtitle="按真实模型调用次数"
      :option="pieOption"
      :loading="loading"
      :empty="!loading && data.length === 0"
      empty-description="暂无模型分布数据"
    />
    <ChartPanel
      title="Token 用量"
      subtitle="输入 / 输出"
      :option="barOption"
      :loading="loading"
      :empty="!loading && data.length === 0"
      empty-description="暂无 Token 用量数据"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { EChartsOption } from "echarts";
import ChartPanel from "./ChartPanel.vue";
import type { ModelStat } from "../api";

const props = defineProps<{
  data: ModelStat[];
  loading?: boolean;
}>();

const colors = ["#89b4fa", "#a6e3a1", "#fab387", "#f38ba8", "#cba6f7", "#89dceb"];

const pieOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
  series: [
    {
      type: "pie",
      radius: ["40%", "70%"],
      center: ["50%", "55%"],
      data: props.data.map((d, i) => ({
        name: d.model || d.virtual_model || "未知",
        value: d.count,
        itemStyle: { color: colors[i % colors.length] },
      })),
      label: { fontSize: 11 },
    },
  ],
}));

const barOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: "axis" },
  grid: { left: 55, right: 20, top: 10, bottom: 30 },
  xAxis: {
    type: "category",
    data: props.data.map((d) => d.model || d.virtual_model || "未知"),
    axisLabel: { fontSize: 10, rotate: props.data.length > 8 ? 30 : 0 },
  },
  yAxis: {
    type: "value",
    name: "tokens",
    axisLabel: {
      formatter: (v: number) => (v >= 1000 ? (v / 1000).toFixed(0) + "K" : String(v)),
    },
  },
  series: [
    {
      name: "输入",
      type: "bar",
      stack: "tokens",
      data: props.data.map((d) => d.total_input_tokens || 0),
      itemStyle: { color: "#89b4fa" },
    },
    {
      name: "输出",
      type: "bar",
      stack: "tokens",
      data: props.data.map((d) => d.total_output_tokens || 0),
      itemStyle: { color: "#a6e3a1" },
    },
  ],
}));
</script>

<style scoped>
.model-charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}
@media (max-width: 900px) {
  .model-charts-row {
    grid-template-columns: 1fr;
  }
}
</style>
