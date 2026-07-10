<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import * as echarts from "echarts/core";
import { BarChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { ModelStatReal } from "@/api/types";
import { useAppStore } from "@/stores/app";

echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

const props = defineProps<{ data: ModelStatReal[] }>();
const el = ref<HTMLDivElement | null>(null);
let chart: echarts.ECharts | null = null;
const app = useAppStore();

function render() {
  if (!el.value) return;
  if (!chart) chart = echarts.init(el.value);
  const styles = getComputedStyle(document.documentElement);
  const text = styles.getPropertyValue("--chart-axis").trim();
  const grid = styles.getPropertyValue("--chart-grid").trim();
  const bar = styles.getPropertyValue("--chart-bar").trim();
  const rows = [...props.data].sort((a, b) => b.count - a.count).slice(0, 12);
  chart.setOption({
    color: [bar],
    textStyle: { fontFamily: "IBM Plex Mono, monospace", color: text },
    grid: { left: 16, right: 24, top: 8, bottom: 8, containLabel: true },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    xAxis: {
      type: "value",
      splitLine: { lineStyle: { color: grid } },
      axisLabel: { color: text },
    },
    yAxis: {
      type: "category",
      data: rows.map((r) => r.model).reverse(),
      axisLabel: {
        color: text,
        width: 120,
        overflow: "truncate",
      },
    },
    series: [
      {
        type: "bar",
        data: rows.map((r) => r.count).reverse(),
        barMaxWidth: 16,
        itemStyle: { borderRadius: [0, 4, 4, 0] },
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
  <div v-if="!data.length" class="empty-state">暂无真实模型数据</div>
  <div v-else ref="el" class="chart" />
</template>

<style scoped>
.chart {
  width: 100%;
  height: 260px;
}
</style>
