<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { DailyStat } from "@/api/types";
import { useAppStore } from "@/stores/app";
import { formatTokens, formatUsd } from "@/utils/format";

echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  CanvasRenderer,
]);

const props = defineProps<{ data: DailyStat[] }>();
const el = ref<HTMLDivElement | null>(null);
let chart: echarts.ECharts | null = null;
let legendSelected: Record<string, boolean> = {};
const app = useAppStore();

function themeColors() {
  const styles = getComputedStyle(document.documentElement);
  return {
    text: styles.getPropertyValue("--chart-axis").trim(),
    grid: styles.getPropertyValue("--chart-grid").trim(),
    muted: styles.getPropertyValue("--text-muted").trim(),
    series: Array.from({ length: 5 }, (_, index) =>
      styles.getPropertyValue(`--chart-series-${index + 1}`).trim(),
    ),
  };
}

function render() {
  if (!el.value) return;
  if (!chart) {
    chart = echarts.init(el.value);
    chart.on("legendselectchanged", (event: unknown) => {
      const selected = (event as { selected?: Record<string, boolean> }).selected;
      if (selected) legendSelected = { ...selected };
    });
  }
  const c = themeColors();
  const days = props.data.map((d) => d.day.slice(5));
  chart.setOption({
    color: c.series,
    textStyle: { fontFamily: "IBM Plex Mono, monospace", color: c.text },
    grid: { left: 56, right: 64, top: 48, bottom: 36 },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line" },
    },
    legend: {
      data: ["成本", "缓存写入", "缓存读取", "输入", "输出"],
      selected: legendSelected,
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
        name: "Token",
        splitLine: { lineStyle: { color: c.grid } },
        axisLabel: {
          color: c.text,
          formatter: (value: number) => formatTokens(value),
        },
      },
      {
        type: "value",
        name: "USD",
        splitLine: { show: false },
        axisLabel: {
          color: c.text,
          formatter: (value: number) => formatUsd(value),
        },
      },
    ],
    series: [
      {
        name: "成本",
        type: "line",
        yAxisIndex: 1,
        smooth: true,
        showSymbol: false,
        lineStyle: { type: "dashed", width: 2 },
        data: props.data.map((d) => d.cost_usd ?? 0),
        tooltip: { valueFormatter: (value: unknown) => formatUsd(Number(value)) },
      },
      {
        name: "缓存写入",
        type: "line",
        smooth: true,
        showSymbol: false,
        data: props.data.map((d) => d.cache_write_tokens ?? 0),
        tooltip: { valueFormatter: (value: unknown) => `${formatTokens(Number(value))} Token` },
      },
      {
        name: "缓存读取",
        type: "line",
        smooth: true,
        showSymbol: false,
        data: props.data.map((d) => d.cache_read_tokens ?? 0),
        areaStyle: { opacity: 0.12 },
        tooltip: { valueFormatter: (value: unknown) => `${formatTokens(Number(value))} Token` },
      },
      {
        name: "输入",
        type: "line",
        smooth: true,
        showSymbol: false,
        data: props.data.map((d) => d.input_tokens ?? 0),
        tooltip: { valueFormatter: (value: unknown) => `${formatTokens(Number(value))} Token` },
      },
      {
        name: "输出",
        type: "line",
        smooth: true,
        showSymbol: false,
        data: props.data.map((d) => d.output_tokens ?? 0),
        tooltip: { valueFormatter: (value: unknown) => `${formatTokens(Number(value))} Token` },
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
  height: 320px;
}
</style>
