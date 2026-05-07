<template>
  <div class="dashboard">
    <div class="top-bar">
      <h2>仪表盘</h2>
      <div class="top-bar-right">
        <label class="toggle-label">
          <input type="checkbox" v-model="autoRefresh" />
          自动刷新
        </label>
        <button class="refresh-btn" @click="loadAll">刷新</button>
      </div>
    </div>

    <StatsCards v-if="summary" :summary="summary" />

    <TrendChart />

    <ModelChart />

    <section class="section">
      <div class="section-header">
        <h3>最近调用</h3>
        <select v-model="filterModel" @change="changePage(1)" class="filter-select">
          <option value="">全部模型</option>
          <option v-for="m in uniqueModels" :key="m" :value="m">{{ m }}</option>
        </select>
      </div>
      <CallsTable
        :calls="calls"
        :total="total"
        :page="page"
        :size="size"
        @select="showDetail"
        @page="changePage"
      />
    </section>

    <CallDetail :call="detail" @close="detail = null" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import type { CallRecord, Summary } from "../api";
import { fetchSummary, fetchCalls, fetchCallDetail } from "../api";
import StatsCards from "../components/StatsCards.vue";
import TrendChart from "../components/TrendChart.vue";
import ModelChart from "../components/ModelChart.vue";
import CallsTable from "../components/CallsTable.vue";
import CallDetail from "../components/CallDetail.vue";

const summary = ref<Summary | null>(null);
const calls = ref<CallRecord[]>([]);
const total = ref(0);
const page = ref(1);
const size = ref(50);
const detail = ref<CallRecord | null>(null);
const filterModel = ref("");
const autoRefresh = ref(true);

let timer: ReturnType<typeof setInterval>;

const uniqueModels = computed(() => {
  const s = new Set(calls.value.map((c) => c.virtual_model));
  return [...s].sort();
});

async function loadAll() {
  summary.value = await fetchSummary();
  await loadCalls();
}

async function loadCalls() {
  const data = await fetchCalls(page.value, size.value, filterModel.value);
  calls.value = data.data;
  total.value = data.total;
}

function changePage(p: number) {
  page.value = p;
  loadCalls();
}

async function showDetail(id: string) {
  detail.value = await fetchCallDetail(id);
}

watch(autoRefresh, (on) => {
  clearInterval(timer);
  if (on) timer = setInterval(loadAll, 10_000);
});

onMounted(() => {
  loadAll();
  if (autoRefresh.value) timer = setInterval(loadAll, 10_000);
});

onUnmounted(() => clearInterval(timer));
</script>

<style scoped>
.dashboard { padding: 0 8px; }
.top-bar {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 20px;
}
.top-bar h2 { font-size: 20px; }
.top-bar-right { display: flex; align-items: center; gap: 16px; }
.toggle-label {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px; color: #a6adc8; cursor: pointer;
}
.toggle-label input { cursor: pointer; }
.refresh-btn {
  background: #313244; color: #cdd6f4; border: none;
  padding: 6px 14px; border-radius: 4px; cursor: pointer; font-size: 13px;
}
.refresh-btn:hover { background: #45475a; }
.section { margin-bottom: 24px; }
.section-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px;
}
.section-header h3 { font-size: 15px; color: #cdd6f4; }
.filter-select {
  background: #313244; color: #cdd6f4; border: 1px solid #45475a;
  padding: 4px 10px; border-radius: 4px; font-size: 13px;
}
</style>
