<template>
  <div class="dashboard">
    <PageHeader title="仪表盘" subtitle="实时监控路由调用与模型状态">
      <template #actions>
        <div class="mode-toggle" title="全局路由模式">
          <button
            type="button"
            class="mode-btn"
            :class="{ active: configStore.routerConfig.mode === 'failover' }"
            :disabled="modeSwitchDisabled"
            @click="switchMode('failover')"
          >
            故障转移
          </button>
          <button
            type="button"
            class="mode-btn"
            :class="{ active: configStore.routerConfig.mode === 'sticky' }"
            :disabled="modeSwitchDisabled"
            @click="switchMode('sticky')"
          >
            指定模型
          </button>
        </div>
        <AutoRefreshControl />
        <UiButton variant="primary" :loading="metrics.refreshing || calls.refreshing" @click="() => refresh()">
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
import { useConfigStore } from "../stores/config";
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
const configStore = useConfigStore();
const toast = useToast();
const route = useRoute();
const router = useRouter();
const modeSaving = ref(false);
const modeSwitchDisabled = computed(
  () => modeSaving.value || configStore.loading || !configStore.configReady
);

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

async function refresh(silent = false) {
  try {
    await Promise.all([
      metrics.loadAll(trendDays.value, { silent }),
      calls.loadCalls({ silent }),
    ]);
  } catch {
    // errors handled by stores
  }
}

async function switchMode(mode: "failover" | "sticky") {
  if (
    configStore.routerConfig.mode === mode ||
    modeSaving.value ||
    configStore.loading ||
    !configStore.configReady
  ) {
    return;
  }
  modeSaving.value = true;
  try {
    const ok = await configStore.setRouterMode(mode);
    if (ok) {
      toast.success(mode === "sticky" ? "已切换为指定模型模式" : "已切换为故障转移模式");
    } else {
      toast.error(configStore.error || "切换路由模式失败，请先在虚拟模型中选择指定项");
    }
  } catch (err) {
    toast.error(err instanceof Error ? err.message : "切换路由模式失败");
  } finally {
    modeSaving.value = false;
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
  configStore.loadConfig().catch(() => {
    /* 模式开关依赖配置；失败时保持默认 failover */
  });
  autoRefresh.start();
  unregisterRefresh = autoRefresh.register(() => refresh(true));
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
.mode-toggle {
  display: inline-flex;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}
.mode-btn {
  appearance: none;
  border: 0;
  background: transparent;
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  padding: 6px 12px;
  cursor: pointer;
}
.mode-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.mode-btn.active {
  background: var(--color-primary-muted);
  color: var(--color-text);
  font-weight: var(--font-medium);
}
</style>
