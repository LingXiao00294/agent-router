import { defineStore } from "pinia";
import { useAutoRefresh, intervals } from "../composables/useAutoRefresh";

export const useAutoRefreshStore = defineStore("autoRefresh", () => {
  const {
    enabled,
    intervalMs,
    lastTick,
    register,
    setEnabled,
    setIntervalMs,
    start,
    stop,
  } = useAutoRefresh();

  return {
    enabled,
    intervalMs,
    intervals,
    lastTick,
    register,
    setEnabled,
    setIntervalMs,
    start,
    stop,
  };
});
