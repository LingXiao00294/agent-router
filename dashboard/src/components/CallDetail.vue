<template>
  <UiModal
    :open="!!call"
    title="调用详情"
    size="lg"
    @close="$emit('close')"
  >
    <div v-if="call" class="call-detail">
      <div class="detail-grid">
        <div class="kv"><span class="key">ID</span><span class="value">{{ call.id }}</span></div>
        <div class="kv"><span class="key">时间</span><span class="value">{{ fmt(call.timestamp) }}</span></div>
        <div class="kv"><span class="key">虚拟模型</span><span class="value">{{ call.virtual_model }}</span></div>
        <div class="kv"><span class="key">Provider</span><span class="value">{{ call.provider_name || call.provider_type || "-" }}</span></div>
        <div class="kv"><span class="key">模型</span><span class="value">{{ call.provider_model || "-" }}</span></div>
        <div class="kv"><span class="key">尝试次数</span><span class="value">{{ call.attempt }}</span></div>
        <div class="kv">
          <span class="key">状态</span>
          <UiBadge :variant="call.status === 'success' ? 'success' : 'error'" size="sm">
            {{ call.status }}
          </UiBadge>
        </div>
        <div class="kv"><span class="key">延迟</span><span class="value">{{ call.latency_ms ?? "-" }}ms</span></div>
      </div>

      <div v-if="failoverList.length" class="detail-section">
        <h4 class="section-title">故障转移链路</h4>
        <div class="failover-chain">
          <div v-for="(fo, i) in failoverList" :key="i" class="failover-entry">
            <span class="failover-step">{{ i + 1 }}</span>
            <span class="failover-provider">{{ fo.provider }}</span>
            <span class="failover-model">{{ fo.model }}</span>
            <span class="failover-error" :title="fo.error">{{ fo.error }}</span>
            <span v-if="fo.latency_ms != null" class="failover-latency">{{ fo.latency_ms }}ms</span>
          </div>
          <div class="failover-entry success">
            <span class="failover-step">{{ failoverList.length + 1 }}</span>
            <span class="failover-provider">{{ call.provider_name || call.provider_type }}</span>
            <span class="failover-model">{{ call.provider_model }}</span>
            <span class="failover-ok">成功</span>
            <span v-if="call.latency_ms != null" class="failover-latency">{{ call.latency_ms }}ms</span>
          </div>
        </div>
      </div>

      <div class="detail-grid">
        <div class="kv"><span class="key">输入 Token</span><span class="value">{{ call.input_tokens ?? "-" }}</span></div>
        <div class="kv"><span class="key">输出 Token</span><span class="value">{{ call.output_tokens ?? "-" }}</span></div>
        <div class="kv"><span class="key">Cache 读取</span><span class="value">{{ call.cache_read_tokens ?? "-" }}</span></div>
        <div class="kv"><span class="key">Cache 写入</span><span class="value">{{ call.cache_write_tokens ?? "-" }}</span></div>
        <div class="kv"><span class="key">费用</span><span class="value">${{ (call.cost_usd || 0).toFixed(6) }}</span></div>
        <div class="kv"><span class="key">请求估算 Token</span><span class="value">{{ call.request_tokens ?? "-" }}</span></div>
      </div>

      <div v-if="call.error_message" class="detail-section">
        <h4 class="section-title">错误信息</h4>
        <pre class="code-block error-block">{{ call.error_message }}</pre>
      </div>

      <JsonPanel v-if="call.request_body" title="请求体" :raw="call.request_body" />
      <JsonPanel v-if="call.response_body" title="响应体" :raw="call.response_body" />
    </div>
  </UiModal>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { CallRecord, FailoverEntry } from "../api";
import UiModal from "./ui/UiModal.vue";
import UiBadge from "./ui/UiBadge.vue";
import JsonPanel from "./JsonPanel.vue";

const props = defineProps<{ call: CallRecord | null }>();
defineEmits<{ close: [] }>();

const failoverList = computed<FailoverEntry[]>(() => {
  if (!props.call?.failover_details) return [];
  try {
    return JSON.parse(props.call.failover_details);
  } catch {
    return [];
  }
});

function fmt(ts: string) {
  return ts ? new Date(ts).toLocaleString() : "-";
}
</script>

<style scoped>
.call-detail {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}
.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
}
.kv {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-2) var(--space-3);
  background: var(--color-surface-elevated);
  border-radius: var(--radius-md);
  gap: var(--space-3);
}
.key {
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}
.value {
  color: var(--color-text-default);
  font-size: var(--text-base);
  font-family: var(--font-mono);
  word-break: break-all;
  text-align: right;
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.section-title {
  font-size: var(--text-md);
  font-weight: var(--font-semibold);
  color: var(--color-text-secondary);
  margin: 0;
}

.failover-chain {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.failover-entry {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: var(--color-surface-elevated);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  border-left: 3px solid var(--color-danger);
}
.failover-entry.success {
  border-left-color: var(--color-success);
}
.failover-step {
  background: var(--color-surface0);
  color: var(--color-text-muted);
  min-width: 20px;
  text-align: center;
  border-radius: var(--radius-sm);
  padding: 1px 4px;
  font-size: var(--text-xs);
}
.failover-provider {
  color: var(--color-text-default);
  font-weight: var(--font-semibold);
}
.failover-model {
  color: var(--color-text-muted);
}
.failover-error {
  color: var(--color-danger);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.failover-ok {
  color: var(--color-success);
}
.failover-latency {
  color: var(--color-text-muted);
  white-space: nowrap;
}

.code-block {
  background: var(--color-crust);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 260px;
  overflow: auto;
  font-family: var(--font-mono);
}
.error-block {
  color: var(--color-danger);
}

@media (max-width: 640px) {
  .detail-grid {
    grid-template-columns: 1fr;
  }
}
</style>
