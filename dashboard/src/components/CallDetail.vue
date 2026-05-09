<template>
  <Teleport to="body">
    <div v-if="call" class="modal-overlay" @click.self="$emit('close')">
      <div class="modal">
        <div class="modal-header">
          <h3>调用详情</h3>
          <button @click="$emit('close')" class="close-btn">&times;</button>
        </div>

        <div class="detail-grid">
          <div class="kv"><span class="key">ID</span><span class="value">{{ call.id }}</span></div>
          <div class="kv"><span class="key">时间</span><span class="value">{{ fmt(call.timestamp) }}</span></div>
          <div class="kv"><span class="key">虚拟模型</span><span class="value">{{ call.virtual_model }}</span></div>
          <div class="kv"><span class="key">Provider</span><span class="value">{{ call.provider_name || call.provider_type || "-" }}</span></div>
          <div class="kv"><span class="key">模型</span><span class="value">{{ call.provider_model || "-" }}</span></div>
          <div class="kv"><span class="key">尝试次数</span><span class="value">{{ call.attempt }}</span></div>
          <div class="kv">
            <span class="key">状态</span>
            <span class="value" :class="call.status === 'success' ? 'text-green' : 'text-red'">
              {{ call.status }}
            </span>
          </div>
        </div>

        <div v-if="failoverList.length" class="section failover-section">
          <h4>故障转移链路</h4>
          <div class="failover-chain">
            <div v-for="(fo, i) in failoverList" :key="i" class="failover-entry">
              <span class="failover-step">{{ i + 1 }}</span>
              <span class="failover-provider">{{ fo.provider }}</span>
              <span class="failover-model">{{ fo.model }}</span>
              <span class="failover-error">{{ fo.error }}</span>
              <span v-if="fo.latency_ms != null" class="failover-latency">{{ fo.latency_ms }}ms</span>
            </div>
            <div class="failover-entry success">
              <span class="failover-step">{{ failoverList.length + 1 }}</span>
              <span class="failover-provider">{{ call.provider_name || call.provider_type }}</span>
              <span class="failover-model">{{ call.provider_model }}</span>
              <span class="failover-ok">✓ 成功</span>
              <span v-if="call.latency_ms != null" class="failover-latency">{{ call.latency_ms }}ms</span>
            </div>
          </div>
        </div>

        <div class="detail-grid">
          <div class="kv"><span class="key">延迟</span><span class="value">{{ call.latency_ms }}ms</span></div>
          <div class="kv"><span class="key">输入 Token</span><span class="value">{{ call.input_tokens ?? "-" }}</span></div>
          <div class="kv"><span class="key">输出 Token</span><span class="value">{{ call.output_tokens ?? "-" }}</span></div>
          <div class="kv"><span class="key">Cache 读取</span><span class="value">{{ call.cache_read_tokens ?? "-" }}</span></div>
          <div class="kv"><span class="key">Cache 写入</span><span class="value">{{ call.cache_write_tokens ?? "-" }}</span></div>
          <div class="kv"><span class="key">费用</span><span class="value">${{ (call.cost_usd || 0).toFixed(6) }}</span></div>
        </div>

        <div v-if="call.error_message" class="section">
          <h4>错误信息</h4>
          <pre class="code-block error-block">{{ call.error_message }}</pre>
        </div>

        <div v-if="call.request_body" class="section">
          <h4>请求体</h4>
          <pre class="code-block">{{ fmtJson(call.request_body) }}</pre>
        </div>

        <div v-if="call.response_body" class="section">
          <h4>响应体</h4>
          <pre class="code-block">{{ fmtJson(call.response_body) }}</pre>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { CallRecord, FailoverEntry } from "../api";

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
function fmtJson(raw: any) {
  try {
    const obj = typeof raw === "string" ? JSON.parse(raw) : JSON.parse(JSON.stringify(raw));
    if (obj.messages) {
      obj.messages = obj.messages.map((m: any) => {
        if (typeof m.content === "string" && m.content.length > 500) {
          return { ...m, content: m.content.slice(0, 500) + "...[截断]" };
        }
        return m;
      });
    }
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(raw);
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.65);
  display: flex; align-items: center; justify-content: center;
  z-index: 100;
}
.modal {
  background: #1e1e2e; border: 1px solid #313244;
  border-radius: 8px; padding: 20px;
  max-width: 900px; max-height: 85vh; overflow: auto;
  width: 95%;
}
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.close-btn { background: none; border: none; color: #cdd6f4; font-size: 24px; cursor: pointer; }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 16px; }
.kv { display: flex; justify-content: space-between; padding: 6px 8px; background: #11111b; border-radius: 4px; }
.key { color: #6c7086; font-size: 12px; }
.value { color: #cdd6f4; font-size: 13px; font-family: monospace; }
.text-green { color: #a6e3a1; }
.text-red { color: #f38ba8; }
.section { margin-bottom: 12px; }
.section h4 { color: #a6adc8; font-size: 13px; margin-bottom: 6px; }
.code-block {
  background: #11111b; border-radius: 4px; padding: 12px;
  font-size: 12px; color: #bac2de; white-space: pre-wrap; word-break: break-all;
  max-height: 300px; overflow: auto;
}
.error-block { color: #f38ba8; }
.failover-chain { display: flex; flex-direction: column; gap: 4px; }
.failover-entry {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px; background: #11111b; border-radius: 4px;
  font-size: 12px; border-left: 3px solid #f38ba8;
}
.failover-entry.success { border-left-color: #a6e3a1; }
.failover-step {
  background: #313244; color: #a6adc8; min-width: 20px;
  text-align: center; border-radius: 3px; padding: 1px 4px; font-size: 11px;
}
.failover-provider { color: #cdd6f4; font-weight: 600; }
.failover-model { color: #6c7086; }
.failover-error { color: #f38ba8; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.failover-ok { color: #a6e3a1; }
.failover-latency { color: #6c7086; white-space: nowrap; }
@media (max-width: 600px) {
  .detail-grid { grid-template-columns: 1fr; }
}
</style>
