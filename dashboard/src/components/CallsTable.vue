<template>
  <div class="calls-table-container">
    <h3>最近调用</h3>
    <table v-if="calls.length">
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
        <tr v-for="call in calls" :key="call.id" @click="$emit('select', call.id)" class="clickable">
          <td>{{ formatTime(call.timestamp) }}</td>
          <td>{{ call.virtual_model }}</td>
          <td>{{ call.provider_name || call.provider_type || "-" }}</td>
          <td>{{ call.provider_model || "-" }}</td>
          <td>
            <span :class="call.status === 'success' ? 'badge-success' : 'badge-error'">
              {{ call.status === "success" ? "✓" : "✗" }}
            </span>
          </td>
          <td>{{ call.latency_ms }}ms</td>
          <td>{{ formatTokens(call.input_tokens) }}</td>
          <td>{{ formatTokens(call.cache_read_tokens) }}</td>
          <td>{{ formatTokens(call.output_tokens) }}</td>
          <td>${{ (call.cost_usd || 0).toFixed(6) }}</td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty">暂无调用记录</div>
    <div class="pagination" v-if="total > size">
      <button :disabled="page <= 1" @click="$emit('page', page - 1)">上一页</button>
      <span>第 {{ page }} / {{ Math.ceil(total / size) }} 页 (共 {{ total }} 条)</span>
      <button :disabled="page >= Math.ceil(total / size)" @click="$emit('page', page + 1)">下一页</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { CallRecord } from "../api";

defineProps<{
  calls: CallRecord[];
  total: number;
  page: number;
  size: number;
}>();

defineEmits<{
  select: [id: string];
  page: [page: number];
}>();

function formatTime(ts: string): string {
  if (!ts) return "-";
  return new Date(ts).toLocaleString("zh-CN");
}

function formatTokens(n: number | null): string {
  if (n == null) return "-";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}
</script>

<style scoped>
.calls-table-container {
  background: #1e1e2e;
  border: 1px solid #313244;
  border-radius: 8px;
  padding: 16px;
}
h3 { margin: 0 0 12px; color: #cdd6f4; font-size: 16px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #313244; color: #bac2de; }
th { color: #a6adc8; font-weight: 600; }
tr.clickable { cursor: pointer; }
tr.clickable:hover { background: #313244; }
.badge-success { color: #a6e3a1; }
.badge-error { color: #f38ba8; }
.empty { text-align: center; color: #6c7086; padding: 24px; }
.pagination { display: flex; justify-content: center; align-items: center; gap: 16px; margin-top: 12px; color: #bac2de; font-size: 13px; }
.pagination button { background: #313244; color: #cdd6f4; border: none; padding: 6px 14px; border-radius: 4px; cursor: pointer; }
.pagination button:disabled { opacity: 0.4; cursor: default; }
.pagination button:not(:disabled):hover { background: #45475a; }
</style>
