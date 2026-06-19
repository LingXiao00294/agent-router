<template>
  <div class="dashboard">
    <PageHeader title="仪表盘" subtitle="实时监控路由调用与模型状态">
      <template #actions>
        <AutoRefreshControl />
        <UiButton variant="primary" :loading="metrics.loading || calls.loading" @click="refresh">
          <template #icon>↻</template>
          刷新
        </UiButton>
      </template>
    </PageHeader>

    <UiErrorBanner
      v-if="metrics.error"
      :message="metrics.error"
      retry
      class="global-error"
      @retry="refresh"
    />

    <StatsCards :summary="metrics.summary" :loading="metrics.loading" />

    <TrendChart v-model:days="trendDays" :data="metrics.dailyTrend" :loading="metrics.loading" />

    <ModelChart :data="metrics.byRealModel" :loading="metrics.loading" />

    <div class="filter-bar">
      <ModelFilter
        ref="modelFilterRef"
        v-model:model-value="filterModelProxy"
        v-model:status-value="filterStatusProxy"
        :models="modelOptions"
      />
      <UiButton size="sm" variant="ghost" @click="clearFilters">清除筛选</UiButton>
    </div>

    <CallsTable
      :calls="calls.calls"
      :total="calls.total"
      :page="calls.page"
      :size="calls.size"
      :pages="calls.pages"
      :loading="calls.loading"
      :error="calls.error"
      :filter-model="calls.filterModel"
      :filter-status="calls.filterStatus"
      @select="showDetail"
      @page="calls.changePage"
      @refresh="calls.loadCalls"
      @clear-filters="clearFilters"
    />

    <CallDetail :call="calls.detail" @close="calls.closeDetail" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useMetricsStore } from "../stores/metrics";
import { useCallsStore } from "../stores/calls";
import { useAutoRefreshStore } from "../stores/autoRefresh";
import { useToast } from "../composables/useToast";
import PageHeader from "../components/PageHeader.vue";
import StatsCards from "../components/StatsCards.vue";
import TrendChart from "../components/TrendChart.vue";
import ModelChart from "../components/ModelChart.vue";
import CallsTable from "../components/CallsTable.vue";
import CallDetail from "../components/CallDetail.vue";
import AutoRefreshControl from "../components/AutoRefreshControl.vue";
import ModelFilter from "../components/ModelFilter.vue";
import UiButton from "../components/ui/UiButton.vue";
import UiErrorBanner from "../components/ui/UiErrorBanner.vue";

const metrics = useMetricsStore();
const calls = useCallsStore();
const autoRefresh = useAutoRefreshStore();
const toast = useToast();
const route = useRoute();
const router = useRouter();

const trendDays = ref(30);
const modelFilterRef = ref<InstanceType<typeof ModelFilter> | null>(null);

const modelOptions = computed(() =>
  [...new Set(calls.calls.map((c) => c.virtual_model))].sort()
);

const filterModelProxy = computed({
  get: () => calls.filterModel,
  set: (v) => calls.setFilterModel(v),
});

const filterStatusProxy = computed({
  get: () => calls.filterStatus,
  set: (v) => calls.setFilterStatus(v),
});

function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  const tag = el.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || el.isContentEditable;
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === "r" || e.key === "R") {
    if (!isTypingTarget(e.target)) {
      e.preventDefault();
      refresh();
    }
  } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    modelFilterRef.value?.focus();
  }
}

async function refresh() {
  try {
    await Promise.all([metrics.loadAll(trendDays.value), calls.loadCalls()]);
  } catch {
    // errors handled by stores
  }
}

function showDetail(id: string) {
  calls.loadDetail(id).catch(() => {
    toast.error("加载调用详情失败");
  });
}

function clearFilters() {
  calls.setFilterModel("");
  calls.setFilterStatus("");
  syncQuery();
}

function syncQuery() {
  const q: Record<string, string> = {};
  if (calls.filterModel) q.model = calls.filterModel;
  if (calls.filterStatus) q.status = calls.filterStatus;
  router.replace({ query: Object.keys(q).length ? q : undefined });
}

watch(
  () => calls.filterModel,
  () => syncQuery()
);
watch(
  () => calls.filterStatus,
  () => syncQuery()
);
watch(trendDays, () => {
  metrics.loadDailyTrend(trendDays.value);
});

let unregisterRefresh: (() => void) | null = null;

onMounted(() => {
  if (route.query.model && typeof route.query.model === "string") {
    calls.filterModel = route.query.model;
  }
  if (route.query.status && typeof route.query.status === "string") {
    calls.filterStatus = route.query.status;
  }

  refresh();
  autoRefresh.start();
  unregisterRefresh = autoRefresh.register(refresh);
  document.addEventListener("keydown", onKeydown);
});

onUnmounted(() => {
  unregisterRefresh?.();
  autoRefresh.stop();
  document.removeEventListener("keydown", onKeydown);
});
</script>

<style scoped>
.dashboard {
  padding: 0 var(--space-1);
}
.global-error {
  margin-bottom: var(--space-4);
}
.filter-bar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
}
</style>
