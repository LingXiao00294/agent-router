<template>
  <div class="chart-container">
    <h3>调用趋势 (近 30 天)</h3>
    <div ref="chartRef" class="chart"></div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import * as echarts from "echarts";
import { fetchDailyTrend } from "../api";

const chartRef = ref<HTMLDivElement>();
let chart: echarts.ECharts | null = null;

async function load() {
  const data = await fetchDailyTrend(30);
  if (!chartRef.value) return;
  if (!chart) {
    chart = echarts.init(chartRef.value, undefined, { renderer: "canvas" });
  }
  chart.setOption({
    tooltip: { trigger: "axis" },
    legend: { data: ["调用总数", "成功", "费用"], textStyle: { color: "#a6adc8" } },
    grid: { left: 50, right: 60, top: 20, bottom: 30 },
    xAxis: {
      type: "category",
      data: data.map((d: any) => d.day),
      axisLine: { lineStyle: { color: "#313244" } },
      axisLabel: { color: "#a6adc8", fontSize: 11 },
    },
    yAxis: [
      {
        type: "value",
        name: "次数",
        nameTextStyle: { color: "#a6adc8" },
        axisLabel: { color: "#a6adc8" },
        splitLine: { lineStyle: { color: "#313244" } },
      },
      {
        type: "value",
        name: "USD",
        nameTextStyle: { color: "#a6adc8" },
        axisLabel: { color: "#a6adc8" },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: "调用总数",
        type: "bar",
        data: data.map((d: any) => d.count),
        itemStyle: { color: "#89b4fa" },
      },
      {
        name: "成功",
        type: "bar",
        data: data.map((d: any) => d.success_count),
        itemStyle: { color: "#a6e3a1" },
      },
      {
        name: "费用",
        type: "line",
        yAxisIndex: 1,
        data: data.map((d: any) => +(d.cost_usd || 0).toFixed(4)),
        lineStyle: { color: "#fab387" },
        itemStyle: { color: "#fab387" },
      },
    ],
  });
}

function onResize() {
  chart?.resize();
}

onMounted(() => {
  load();
  window.addEventListener("resize", onResize);
});

onUnmounted(() => {
  window.removeEventListener("resize", onResize);
  chart?.dispose();
});
</script>

<style scoped>
.chart-container {
  background: #1e1e2e;
  border: 1px solid #313244;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 24px;
}
h3 {
  margin: 0 0 8px;
  color: #cdd6f4;
  font-size: 15px;
}
.chart {
  width: 100%;
  height: 280px;
}
</style>
