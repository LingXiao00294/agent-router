<template>
  <div class="charts-row">
    <div class="chart-container">
      <h3>模型分布 (实际)</h3>
      <div ref="modelRef" class="chart"></div>
    </div>
    <div class="chart-container">
      <h3>Token 用量</h3>
      <div ref="tokenRef" class="chart"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import * as echarts from "echarts";
import { fetchByRealModel } from "../api";

const modelRef = ref<HTMLDivElement>();
const tokenRef = ref<HTMLDivElement>();
let modelChart: echarts.ECharts | null = null;
let tokenChart: echarts.ECharts | null = null;

async function load() {
  let data;
  try {
    data = await fetchByRealModel();
  } catch {
    return;
  }
  if (!data.length) return;

  const colors = ["#89b4fa", "#a6e3a1", "#fab387", "#f38ba8", "#cba6f7"];

  // 模型分布饼图
  if (modelRef.value) {
    if (!modelChart) {
      modelChart = echarts.init(modelRef.value, undefined, { renderer: "canvas" });
    }
    modelChart.setOption({
      tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
      series: [
        {
          type: "pie",
          radius: ["40%", "70%"],
          center: ["50%", "55%"],
          data: data.map((d: any, i: number) => ({
            name: d.model,
            value: d.count,
            itemStyle: { color: colors[i % colors.length] },
          })),
          label: { color: "#a6adc8", fontSize: 11 },
        },
      ],
    });
  }

  // Token 用量柱状图
  if (tokenRef.value) {
    if (!tokenChart) {
      tokenChart = echarts.init(tokenRef.value, undefined, { renderer: "canvas" });
    }
    tokenChart.setOption({
      tooltip: { trigger: "axis" },
      grid: { left: 55, right: 20, top: 10, bottom: 30 },
      xAxis: {
        type: "category",
        data: data.map((d: any) => d.model),
        axisLabel: { color: "#a6adc8", fontSize: 10 },
        axisLine: { lineStyle: { color: "#313244" } },
      },
      yAxis: {
        type: "value",
        name: "tokens",
        axisLabel: {
          color: "#a6adc8",
          formatter: (v: number) => (v >= 1000 ? (v / 1000).toFixed(0) + "K" : String(v)),
        },
        splitLine: { lineStyle: { color: "#313244" } },
      },
      series: [
        {
          name: "输入",
          type: "bar",
          stack: "tokens",
          data: data.map((d: any) => d.total_input_tokens || 0),
          itemStyle: { color: "#89b4fa" },
        },
        {
          name: "输出",
          type: "bar",
          stack: "tokens",
          data: data.map((d: any) => d.total_output_tokens || 0),
          itemStyle: { color: "#a6e3a1" },
        },
        {
          name: "Cache 读取",
          type: "bar",
          stack: "tokens",
          data: data.map((d: any) => d.total_cache_read || 0),
          itemStyle: { color: "#f9e2af" },
        },
        {
          name: "Cache 写入",
          type: "bar",
          stack: "tokens",
          data: data.map((d: any) => d.total_cache_write || 0),
          itemStyle: { color: "#cba6f7" },
        },
      ],
    });
  }
}

function onResize() {
  modelChart?.resize();
  tokenChart?.resize();
}

onMounted(() => {
  load();
  window.addEventListener("resize", onResize);
});

onUnmounted(() => {
  window.removeEventListener("resize", onResize);
  modelChart?.dispose();
  tokenChart?.dispose();
});
</script>

<style scoped>
.charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 24px;
}
.chart-container {
  background: #1e1e2e;
  border: 1px solid #313244;
  border-radius: 8px;
  padding: 16px;
}
h3 {
  margin: 0 0 8px;
  color: #cdd6f4;
  font-size: 15px;
}
.chart {
  width: 100%;
  height: 250px;
}
@media (max-width: 900px) {
  .charts-row {
    grid-template-columns: 1fr;
  }
}
</style>
