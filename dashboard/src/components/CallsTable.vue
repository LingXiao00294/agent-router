<template>
  <UiCard class="calls-table-card" title="最近调用" :subtitle="subtitle">
    <UiErrorBanner
      v-if="error"
      :message="error"
      retry
      class="table-error"
      @retry="$emit('refresh')"
    />

    <div class="table-scroll">
      <table v-if="!loading && calls.length">
        <thead>
          <tr>
            <th>时间</th>
            <th>虚拟模型</th>
            <th>Provider</th>
            <th>模型</th>
            <th>状态</th>
            <th>延迟</th>
            <th>输入 Token</th>
            <th>Cache</th>
            <th>输出 Token</th>
            <th>费用</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="call in calls"
            :key="call.id"
            tabindex="0"
            class="clickable"
            @click="$emit('select', call.id)"
            @keydown.enter="$emit('select', call.id)"
          >
            <td>{{ formatTime(call.timestamp) }}</td>
            <td>{{ call.virtual_model }}</td>
            <td>
              {{ call.provider_name || call.provider_type || "-" }}
              <UiBadge
                v-if="call.attempt > 1"
                size="sm"
                variant="warning"
                :title="`经过 ${call.attempt} 次尝试`"
              >
                →{{ call.attempt }}
              </UiBadge>
            </td>
            <td>{{ call.provider_model || "-" }}</td>
            <td>
              <UiBadge :variant="call.status === 'success' ? 'success' : 'error'" size="sm">
                {{ call.status === "success" ? "成功" : call.status }}
              </UiBadge>
            </td>
            <td>{{ call.latency_ms ?? "-" }}ms</td>
            <td>{{ formatTokens(call.input_tokens) }}</td>
            <td>{{ formatTokens(call.cache_read_tokens) }}</td>
            <td>{{ formatTokens(call.output_tokens) }}</td>
            <td>${{ (call.cost_usd || 0).toFixed(6) }}</td>
          </tr>
        </tbody>
      </table>

      <div v-else-if="loading" class="skeleton-rows">
        <UiSkeleton v-for="i in 6" :key="i" variant="rect" class="skeleton-row" />
      </div>

      <UiEmpty
        v-else
        title="暂无调用记录"
        :description="emptyDescription"
      >
        <template v-if="hasFilters" #action>
          <UiButton size="sm" variant="ghost" @click="emit('clearFilters')">清除筛选</UiButton>
        </template>
      </UiEmpty>
    </div>

    <div v-if="pages > 1" class="pagination">
      <UiButton
        size="sm"
        variant="secondary"
        :disabled="page <= 1"
        @click="$emit('page', page - 1)"
      >
        上一页
      </UiButton>
      <span class="page-info">第 {{ page }} / {{ pages }} 页 (共 {{ total }} 条)</span>
      <UiButton
        size="sm"
        variant="secondary"
        :disabled="page >= pages"
        @click="$emit('page', page + 1)"
      >
        下一页
      </UiButton>
    </div>
  </UiCard>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { CallRecord } from "../api";
import UiCard from "./ui/UiCard.vue";
import UiBadge from "./ui/UiBadge.vue";
import UiSkeleton from "./ui/UiSkeleton.vue";
import UiEmpty from "./ui/UiEmpty.vue";
import UiButton from "./ui/UiButton.vue";
import UiErrorBanner from "./ui/UiErrorBanner.vue";

const props = defineProps<{
  calls: CallRecord[];
  total: number;
  page: number;
  size: number;
  pages: number;
  loading?: boolean;
  error?: string | null;
  filterModel?: string;
  filterStatus?: string;
}>();

const emit = defineEmits<{
  select: [id: string];
  page: [page: number];
  refresh: [];
  clearFilters: [];
}>();

const hasFilters = computed(() => !!props.filterModel || !!props.filterStatus);
const emptyDescription = computed(() =>
  hasFilters.value ? "当前筛选条件下没有匹配记录" : "系统开始运行后，调用记录会显示在这里"
);
const subtitle = computed(() => (props.total ? `共 ${props.total} 条记录` : ""));

function formatTime(ts: string): string {
  if (!ts) return "-";
  return new Date(ts).toLocaleString();
}

function formatTokens(n: number | null): string {
  if (n == null) return "-";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}
</script>

<style scoped>
.calls-table-card {
  margin-bottom: var(--space-6);
}
.table-error {
  margin-bottom: var(--space-4);
}
.table-scroll {
  overflow-x: auto;
}
table {
  width: 100%;
  min-width: 760px;
  border-collapse: collapse;
  font-size: var(--text-base);
}
th,
td {
  padding: var(--space-3) var(--space-4);
  text-align: left;
  border-bottom: 1px solid var(--color-border);
  color: var(--color-text-secondary);
  white-space: nowrap;
}
th {
  color: var(--color-text-muted);
  font-weight: var(--font-semibold);
  background: var(--color-surface-elevated);
}
tr.clickable {
  cursor: pointer;
  transition: background var(--transition-fast);
}
tr.clickable:hover,
tr.clickable:focus-visible {
  background: var(--color-surface-hover);
}

.skeleton-rows {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-3) 0;
}
.skeleton-row {
  height: 40px;
  border-radius: var(--radius-md);
}

.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: var(--space-4);
  margin-top: var(--space-4);
  color: var(--color-text-secondary);
  font-size: var(--text-base);
}
.page-info {
  font-size: var(--text-sm);
}
</style>
