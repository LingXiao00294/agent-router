import { defineStore } from "pinia";
import { ref, computed } from "vue";
import {
  fetchSummary,
  fetchByModel,
  fetchByRealModel,
  fetchByProvider,
  fetchDailyTrend,
  type Summary,
  type ModelStat,
  type ProviderStat,
  type DailyStat,
} from "../api";

export const useMetricsStore = defineStore("metrics", () => {
  const summary = ref<Summary | null>(null);
  const byModel = ref<ModelStat[]>([]);
  const byRealModel = ref<ModelStat[]>([]);
  const byProvider = ref<ProviderStat[]>([]);
  const dailyTrend = ref<DailyStat[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const lastUpdated = ref<Date | null>(null);

  const hasData = computed(() => !!summary.value);

  async function loadSummary() {
    summary.value = await fetchSummary();
  }

  async function loadByModel() {
    byModel.value = await fetchByModel();
  }

  async function loadByRealModel() {
    byRealModel.value = await fetchByRealModel();
  }

  async function loadByProvider() {
    byProvider.value = await fetchByProvider();
  }

  async function loadDailyTrend(days = 30) {
    dailyTrend.value = await fetchDailyTrend(days);
  }

  async function loadAll(days = 30) {
    loading.value = true;
    error.value = null;
    try {
      await Promise.all([
        loadSummary(),
        loadByModel(),
        loadByRealModel(),
        loadByProvider(),
        loadDailyTrend(days),
      ]);
      lastUpdated.value = new Date();
    } catch (err) {
      error.value = err instanceof Error ? err.message : "加载指标失败";
      throw err;
    } finally {
      loading.value = false;
    }
  }

  function reset() {
    summary.value = null;
    byModel.value = [];
    byRealModel.value = [];
    byProvider.value = [];
    dailyTrend.value = [];
    error.value = null;
    lastUpdated.value = null;
  }

  return {
    summary,
    byModel,
    byRealModel,
    byProvider,
    dailyTrend,
    loading,
    error,
    lastUpdated,
    hasData,
    loadSummary,
    loadByModel,
    loadByRealModel,
    loadByProvider,
    loadDailyTrend,
    loadAll,
    reset,
  };
});
