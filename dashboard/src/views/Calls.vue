<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { storeToRefs } from "pinia";
import { useCallsStore } from "@/stores/calls";
import { useMetricsStore } from "@/stores/metrics";
import CallDetail from "@/components/CallDetail.vue";
import {
  formatActualModel,
  formatLatency,
  formatNumber,
  formatTime,
  formatTokens,
  formatUsd,
  parsePositiveInt,
} from "@/utils/format";
import { useAutoRefresh } from "@/composables/useAutoRefresh";

const store = useCallsStore();
const route = useRoute();
const router = useRouter();
const { page, loading, error, detail } = storeToRefs(store);
const metrics = useMetricsStore();
const { byRealModel: actualModels } = storeToRefs(metrics);

const filters = computed(() => ({
  page: parsePositiveInt(route.query.page, 1),
  size: parsePositiveInt(route.query.size, 50, 200),
  model: typeof route.query.model === "string" ? route.query.model : "",
  status: typeof route.query.status === "string" ? route.query.status : "",
  provider: typeof route.query.provider === "string" ? route.query.provider : "",
  providerModel:
    typeof route.query.provider_model === "string"
      ? route.query.provider_model
      : "",
}));

function actualModelKey(provider: string, model: string): string {
  return JSON.stringify([provider, model]);
}

const selectedActualModelKey = computed(() => {
  if (!filters.value.provider || !filters.value.providerModel) return "";
  return actualModelKey(filters.value.provider, filters.value.providerModel);
});

function updateActualModelFilter(key: string) {
  const selected = actualModels.value.find(
    (row) => actualModelKey(row.provider, row.model) === key,
  );
  updateQuery({
    provider: selected?.provider,
    provider_model: selected?.model,
    page: 1,
  });
}

async function load(silent = false) {
  const pageNum = filters.value.page;
  const sizeNum = filters.value.size;
  // Normalize invalid query strings (e.g. page=abc) back into the URL.
  const rawPage = route.query.page;
  const rawSize = route.query.size;
  if (
    (rawPage != null && String(rawPage) !== String(pageNum)) ||
    (rawSize != null && String(rawSize) !== String(sizeNum))
  ) {
    updateQuery({ page: pageNum, size: sizeNum });
    return;
  }

  await store.fetchList(
    {
      page: pageNum,
      size: sizeNum,
      model: filters.value.model || undefined,
      status: filters.value.status || undefined,
      provider: filters.value.provider || undefined,
      provider_model: filters.value.providerModel || undefined,
    },
    silent,
  );
  const p = store.page;
  if (p && p.total > 0 && p.data.length === 0 && p.page > p.pages) {
    updateQuery({ page: Math.max(1, p.pages) });
  }
}

function updateQuery(patch: Record<string, string | number | undefined>) {
  const next = { ...route.query };
  for (const [k, v] of Object.entries(patch)) {
    if (v === undefined || v === "") delete next[k];
    else next[k] = String(v);
  }
  void router.replace({ query: next });
}

function openDetail(id: string) {
  updateQuery({ id });
}

function closeDetail() {
  const q = { ...route.query };
  delete q.id;
  void router.replace({ query: q });
}

onMounted(() => {
  void load();
  if (!metrics.loadedOnce) void metrics.refresh(true).catch(() => {});
});

watch(
  () => [
    route.query.page,
    route.query.size,
    route.query.model,
    route.query.status,
    route.query.provider,
    route.query.provider_model,
  ],
  () => {
    void load();
  },
);

useAutoRefresh(async () => {
  await load(true);
  if (store.error) throw new Error(store.error);
});

watch(
  () => route.query.id,
  (id) => {
    if (typeof id === "string") void store.fetchDetail(id);
    else store.clearDetail();
  },
  { immediate: true },
);

const emptyKind = computed(() => {
  if (!page.value) return "loading";
  if (
    page.value.total === 0 &&
    (filters.value.model ||
      filters.value.status ||
      filters.value.provider ||
      filters.value.providerModel)
  ) {
    return "filtered";
  }
  if (page.value.total === 0) return "empty";
  if (page.value.data.length === 0 && page.value.page > 1) return "oob";
  return "data";
});
</script>

<template>
  <div class="page fade-up">
    <header class="page-head">
      <div>
        <h1>Calls</h1>
        <p class="muted">调用记录与故障转移详情</p>
      </div>
    </header>

    <div class="filters panel">
      <div class="field">
        <label>虚拟模型</label>
        <input
          :value="filters.model"
          placeholder="全部"
          @change="updateQuery({ model: ($event.target as HTMLInputElement).value, page: 1 })"
        />
      </div>
      <div class="field">
        <label>状态</label>
        <select
          :value="filters.status"
          @change="updateQuery({ status: ($event.target as HTMLSelectElement).value, page: 1 })"
        >
          <option value="">全部</option>
          <option value="success">success</option>
          <option value="error">error</option>
        </select>
      </div>
      <div class="field">
        <label>真实模型</label>
        <select
          :value="selectedActualModelKey"
          @change="updateActualModelFilter(($event.target as HTMLSelectElement).value)"
        >
          <option value="">全部</option>
          <option
            v-if="selectedActualModelKey && !actualModels.some((r) => actualModelKey(r.provider, r.model) === selectedActualModelKey)"
            :value="selectedActualModelKey"
          >
            {{ formatActualModel(filters.provider, filters.providerModel) }}
          </option>
          <option
            v-for="row in actualModels"
            :key="actualModelKey(row.provider, row.model)"
            :value="actualModelKey(row.provider, row.model)"
          >
            {{ formatActualModel(row.provider, row.model) }}
          </option>
        </select>
      </div>
      <div class="field">
        <label>每页</label>
        <select
          :value="filters.size"
          @change="updateQuery({ size: Number(($event.target as HTMLSelectElement).value), page: 1 })"
        >
          <option :value="20">20</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
        </select>
      </div>
    </div>

    <div v-if="error" class="error-state panel">{{ error }}</div>
    <div v-else-if="loading && !page" class="empty-state panel">加载中…</div>
    <div v-else-if="emptyKind === 'empty'" class="empty-state panel">暂无调用记录</div>
    <div v-else-if="emptyKind === 'filtered'" class="empty-state panel">当前筛选无结果</div>
    <div v-else-if="emptyKind === 'oob'" class="empty-state panel">
      页码超出范围，正在跳转…
    </div>
    <div v-else class="panel table-panel">
      <div class="table-wrap">
        <table class="data">
          <thead>
            <tr>
              <th>时间</th>
              <th>虚拟模型</th>
              <th>Provider</th>
              <th>真实模型</th>
              <th>状态</th>
              <th>延迟</th>
              <th>Token</th>
              <th>Cache</th>
              <th>费用</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in page?.data || []"
              :key="row.id"
              @click="openDetail(row.id)"
            >
              <td class="mono">{{ formatTime(row.timestamp) }}</td>
              <td class="mono">{{ row.virtual_model }}</td>
              <td class="mono">
                {{ row.provider_name || "—" }}
                <span v-if="row.attempt > 1" class="badge badge-warn">failover×{{ row.attempt }}</span>
              </td>
              <td class="mono">
                {{ formatActualModel(row.provider_name, row.provider_model) }}
              </td>
              <td>
                <span
                  class="badge"
                  :class="row.status === 'success' ? 'badge-success' : 'badge-danger'"
                >
                  {{ row.status }}
                </span>
              </td>
              <td class="mono">{{ formatLatency(row.latency_ms) }}</td>
              <td class="mono">
                {{ formatTokens(row.input_tokens) }} /
                {{ formatTokens(row.output_tokens) }}
              </td>
              <td class="mono">
                {{ formatTokens(row.cache_read_tokens) }} /
                {{ formatTokens(row.cache_write_tokens) }}
              </td>
              <td class="mono">{{ formatUsd(row.cost_usd) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="pager">
        <span class="muted mono">
          共 {{ formatNumber(page?.total ?? 0) }} · 第 {{ page?.page }} / {{ page?.pages }} 页
        </span>
        <div class="pager-btns">
          <button
            class="btn btn-sm"
            type="button"
            :disabled="!page || page.page <= 1"
            @click="updateQuery({ page: filters.page - 1 })"
          >
            上一页
          </button>
          <button
            class="btn btn-sm"
            type="button"
            :disabled="!page || page.page >= page.pages"
            @click="updateQuery({ page: filters.page + 1 })"
          >
            下一页
          </button>
        </div>
      </div>
    </div>

    <CallDetail
      v-if="route.query.id"
      :record="detail"
      :loading="store.detailLoading"
      :error="store.detailError"
      @close="closeDetail"
    />
  </div>
</template>

<style scoped>
.page-head h1 {
  margin: 0;
  font-size: 1.5rem;
}
.page-head p {
  margin: 0.25rem 0 0;
}
.filters {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.75rem;
  padding: 0.9rem 1rem;
  margin: 1rem 0;
}
.table-panel {
  padding: 0;
  overflow: hidden;
}
.pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.75rem 1rem;
  border-top: 1px solid var(--border);
}
.pager-btns {
  display: flex;
  gap: 0.4rem;
}
.badge {
  margin-left: 0.35rem;
}
@media (max-width: 800px) {
  .filters {
    grid-template-columns: 1fr;
  }
}
</style>
