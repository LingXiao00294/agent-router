import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { fetchCalls, fetchCallDetail, type CallRecord, type CallsPage } from "../api";

export const useCallsStore = defineStore("calls", () => {
  const calls = ref<CallRecord[]>([]);
  const total = ref(0);
  const page = ref(1);
  const size = ref(50);
  const filterModel = ref("");
  const filterStatus = ref("");
  const loading = ref(false);
  const refreshing = ref(false);
  const error = ref<string | null>(null);
  const detail = ref<CallRecord | null>(null);
  const detailLoading = ref(false);
  const detailError = ref<string | null>(null);

  const pages = computed(() => Math.max(1, Math.ceil(total.value / size.value)));

  async function loadCalls(options: { silent?: boolean } = {}) {
    const silent = options.silent ?? calls.value.length > 0;
    if (!silent) loading.value = true;
    refreshing.value = true;
    error.value = null;
    try {
      const data: CallsPage = await fetchCalls(
        page.value,
        size.value,
        filterModel.value,
        filterStatus.value
      );
      calls.value = data.data;
      total.value = data.total;
    } catch (err) {
      error.value = err instanceof Error ? err.message : "加载调用记录失败";
      throw err;
    } finally {
      loading.value = false;
      refreshing.value = false;
    }
  }

  async function loadDetail(id: string) {
    detailLoading.value = true;
    detailError.value = null;
    try {
      detail.value = await fetchCallDetail(id);
    } catch (err) {
      detailError.value = err instanceof Error ? err.message : "加载详情失败";
      detail.value = null;
      throw err;
    } finally {
      detailLoading.value = false;
    }
  }

  function changePage(p: number) {
    page.value = p;
    return loadCalls();
  }

  function setSize(s: number) {
    size.value = s;
    page.value = 1;
    return loadCalls();
  }

  function setFilterModel(model: string) {
    filterModel.value = model;
    page.value = 1;
    return loadCalls();
  }

  function setFilterStatus(status: string) {
    filterStatus.value = status;
    page.value = 1;
    return loadCalls();
  }

  function closeDetail() {
    detail.value = null;
    detailError.value = null;
  }

  function reset() {
    calls.value = [];
    total.value = 0;
    page.value = 1;
    size.value = 50;
    filterModel.value = "";
    filterStatus.value = "";
    error.value = null;
    detail.value = null;
  }

  return {
    calls,
    total,
    page,
    size,
    pages,
    filterModel,
    filterStatus,
    loading,
    refreshing,
    error,
    detail,
    detailLoading,
    detailError,
    loadCalls,
    loadDetail,
    changePage,
    setSize,
    setFilterModel,
    setFilterStatus,
    closeDetail,
    reset,
  };
});
