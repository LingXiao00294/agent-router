<template>
  <UiCard class="chart-panel" :title="title" :subtitle="subtitle">
    <div v-if="loading" class="chart-loading">
      <UiSkeleton variant="rect" class="skeleton-chart" />
    </div>
    <UiEmpty
      v-else-if="empty"
      :title="emptyTitle"
      :description="emptyDescription"
    />
    <div v-else ref="chartRef" class="chart-canvas" />
  </UiCard>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, computed } from "vue";
import * as echarts from "echarts";
import type { ECharts, EChartsOption } from "echarts";
import { useResizeObserver } from "@vueuse/core";
import UiCard from "./ui/UiCard.vue";
import UiSkeleton from "./ui/UiSkeleton.vue";
import UiEmpty from "./ui/UiEmpty.vue";
import { useChartTheme } from "../composables/useChartTheme";

const props = withDefaults(
  defineProps<{
    title?: string;
    subtitle?: string;
    option: EChartsOption;
    loading?: boolean;
    empty?: boolean;
    emptyTitle?: string;
    emptyDescription?: string;
  }>(),
  {
    title: "",
    subtitle: "",
    loading: false,
    empty: false,
    emptyTitle: "暂无数据",
    emptyDescription: "",
  }
);

const chartRef = ref<HTMLElement | null>(null);
let chart: ECharts | null = null;

const { baseOption, colors } = useChartTheme();

function deepMerge<T extends Record<string, unknown>>(target: T, source: unknown): T {
  if (!source || typeof source !== "object") return target;
  const s = source as Record<string, unknown>;
  for (const key of Object.keys(s)) {
    if (Array.isArray(s[key])) {
      target[key as keyof T] = s[key] as T[keyof T];
    } else if (s[key] && typeof s[key] === "object" && !Array.isArray(target[key as keyof T])) {
      if (!target[key as keyof T]) target[key as keyof T] = {} as T[keyof T];
      deepMerge(target[key as keyof T] as Record<string, unknown>, s[key]);
    } else {
      target[key as keyof T] = s[key] as T[keyof T];
    }
  }
  return target;
}

const mergedOption = computed<EChartsOption>(() =>
  deepMerge(deepMerge({}, baseOption.value) as EChartsOption, props.option) as EChartsOption
);

function initChart() {
  if (!chartRef.value) return;
  chart = echarts.init(chartRef.value, undefined, { renderer: "canvas" });
  chart.setOption(mergedOption.value, true);
}

function disposeChart() {
  if (chart) {
    chart.dispose();
    chart = null;
  }
}

onMounted(() => {
  if (!props.loading && !props.empty) {
    initChart();
  }
});

onUnmounted(disposeChart);

useResizeObserver(chartRef, () => {
  chart?.resize();
});

watch(
  () => [props.loading, props.empty] as const,
  ([loading, empty]) => {
    if (loading || empty) {
      disposeChart();
    } else if (!chart && chartRef.value) {
      initChart();
    }
  }
);

watch(
  mergedOption,
  (opt) => {
    if (chart) {
      chart.setOption(opt, true);
    }
  },
  { deep: true }
);

watch(colors, () => {
  if (chart) {
    chart.setOption(mergedOption.value, true);
  }
});

function exportImage(): string | undefined {
  return chart?.getDataURL({
    type: "png",
    pixelRatio: 2,
    backgroundColor: colors.value.tooltipBg,
  });
}

defineExpose({ exportImage });
</script>

<style scoped>
.chart-panel {
  display: flex;
  flex-direction: column;
}
.chart-loading,
.chart-canvas {
  width: 100%;
  height: 300px;
}
.skeleton-chart {
  height: 100%;
  border-radius: var(--radius-md);
}
</style>
