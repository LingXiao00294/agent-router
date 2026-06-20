import { computed } from "vue";
import { useAppStore } from "../stores/app";

export function useChartTheme() {
  const app = useAppStore();
  const isDark = computed(() => app.resolvedTheme === "dark");

  const colors = computed(() => ({
    text: isDark.value ? "#cdd6f4" : "#4c4f69",
    textSecondary: isDark.value ? "#a6adc8" : "#6c6f85",
    grid: isDark.value ? "#313244" : "#ccd0da",
    tooltipBg: isDark.value ? "#1e1e2e" : "#ffffff",
    tooltipBorder: isDark.value ? "#45475a" : "#bcc0cc",
    series: ["#89b4fa", "#a6e3a1", "#f9e2af", "#f38ba8", "#cba6f7", "#89dceb", "#fab387"],
  }));

  const baseOption = computed(() => ({
    backgroundColor: "transparent",
    textStyle: {
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      color: colors.value.textSecondary,
    },
    title: {
      textStyle: { color: colors.value.text },
      subtextStyle: { color: colors.value.textSecondary },
    },
    legend: {
      textStyle: { color: colors.value.textSecondary },
      pageTextStyle: { color: colors.value.textSecondary },
    },
    tooltip: {
      backgroundColor: colors.value.tooltipBg,
      borderColor: colors.value.tooltipBorder,
      textStyle: { color: colors.value.text },
      extraCssText: "border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,0.16);",
    },
  }));

  const categoryAxis = computed(() => ({
    axisLine: { lineStyle: { color: colors.value.grid } },
    axisTick: { alignWithLabel: true, lineStyle: { color: colors.value.grid } },
    axisLabel: { color: colors.value.textSecondary },
    splitLine: { show: false },
  }));

  const valueAxis = computed(() => ({
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: colors.value.textSecondary },
    splitLine: {
      show: true,
      lineStyle: { color: colors.value.grid, type: "dashed" as const },
    },
  }));

  return { isDark, colors, baseOption, categoryAxis, valueAxis };
}
