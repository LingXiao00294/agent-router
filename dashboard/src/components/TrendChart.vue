<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import * as echarts from "echarts/core";
import { LineChart, BarChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { DailyStat } from "@/api/types";
import { useAppStore } from "@/stores/app";

echarts.use([
  LineChart,
  BarChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  CanvasRenderer,
]);

const props = defineProps<{ data: DailyStat[] }>();
const el = ref<HTMLDivElement | null>(null);
let chart: echarts.ECharts | null = null;
const app = useAppStore();

function themeColors() {
  const styles = getComputedStyle(document.documentElement);
  return {
    text: styles.getPropertyValue("--chart-axis").trim(),
    grid: styles.getPropertyValue("--chart-grid").trim(),
    line: styles.getPropertyValue("--chart-line").trim(),
    bar: styles.getPropertyValue("--chart-bar").trim(),
    muted: styles.getPropertyValue("--text-muted").trim(),
  };
}

function render() {
  if (!el.value) return;
  if (!chart) chart = echarts.init(el.value);
  const c = themeColors();
  const days = props.data.map((d) => d.day.slice(5));
  chart.setOption({
    color: [c.line, c.bar],
    textStyle: { fontFamily: "IBM Plex Mono, monospace", color: c.text },
    grid: { left: 40, right: 16, top: 36, bottom: 28 },
    tooltip: { trigger: "axis" },
    legend: {
      data: ["调用", "费用"],
      textStyle: { color: c.muted },
      top: 0,
    },
    xAxis: {
      type: "category",
      data: days,
      axisLine: { lineStyle: { color: c.grid } },
      axisLabel: { color: c.text },
    },
    yAxis: [
      {
        type: "value",
        name: "calls",
        splitLine: { lineStyle: { color: c.grid } },
        axisLabel: { color: c.text },
      },
      {
        type: "value",
        name: "USD",
        splitLine: { show: false },
        axisLabel: { color: c.text },
      },
    ],
    series: [
      {
        name: "调用",
        type: "bar",
        data: props.data.map((d) => d.count),
        barMaxWidth: 18,
        itemStyle: { borderRadius: [3, 3, 0, 0] },
      },
      {
        name: "费用",
        type: "line",
        yAxisIndex: 1,
        smooth: true,
        showSymbol: false,
        data: props.data.map((d) => d.cost_usd ?? 0),
      },
    ],
  });
}

function onResize() {
  chart?.resize();
}

onMounted(() => {
  render();
  window.addEventListener("resize", onResize);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", onResize);
  chart?.dispose();
  chart = null;
});

watch(() => props.data, render, { deep: true });
watch(() => app.theme, () => {
  chart?.dispose();
  chart = null;
  render();
});
</script>

<template>
  <div ref="el" class="chart" />
</template>

<style scoped>
.chart {
  width: 100%;
  height: 260px;
}
</style>
