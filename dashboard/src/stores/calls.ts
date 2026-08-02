import { ref } from "vue";
import { defineStore } from "pinia";
import * as api from "@/api";
import type { CallRecord, CallsPage } from "@/api/types";

export const useCallsStore = defineStore("calls", () => {
  const page = ref<CallsPage | null>(null);
  const detail = ref<CallRecord | null>(null);
  const loading = ref(false);
  const detailLoading = ref(false);
  const error = ref<string | null>(null);
  const detailError = ref<string | null>(null);
  let listSeq = 0;
  let detailSeq = 0;

  async function fetchList(
    params: {
      page?: number;
      size?: number;
      model?: string;
      status?: string;
      provider?: string;
      provider_model?: string;
    },
    silent = false,
  ) {
    const seq = ++listSeq;
    if (!silent) loading.value = true;
    error.value = null;
    try {
      const result = await api.getCalls(params);
      if (seq !== listSeq) return;
      page.value = result;
    } catch (err) {
      if (seq !== listSeq) return;
      error.value = err instanceof Error ? err.message : "加载调用失败";
      if (!silent) throw err;
    } finally {
      if (seq === listSeq) loading.value = false;
    }
  }

  async function fetchDetail(id: string) {
    const seq = ++detailSeq;
    detailLoading.value = true;
    detailError.value = null;
    try {
      const record = await api.getCall(id);
      if (seq !== detailSeq) return;
      detail.value = record;
    } catch (err) {
      if (seq !== detailSeq) return;
      detail.value = null;
      detailError.value = err instanceof Error ? err.message : "加载详情失败";
    } finally {
      if (seq === detailSeq) detailLoading.value = false;
    }
  }

  function clearDetail() {
    detailSeq += 1;
    detail.value = null;
    detailError.value = null;
    detailLoading.value = false;
  }

  return {
    page,
    detail,
    loading,
    detailLoading,
    error,
    detailError,
    fetchList,
    fetchDetail,
    clearDetail,
  };
});
