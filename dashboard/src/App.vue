<template>
  <div class="app">
    <header class="header">
      <h1>Agent Router Dashboard</h1>
      <span class="version">v0.1.0</span>
    </header>

    <main class="main">
      <StatsCards v-if="summary" :summary="summary" />

      <section class="section">
        <CallsTable
          :calls="calls"
          :total="total"
          :page="page"
          :size="size"
          @select="showDetail"
          @page="changePage"
        />
      </section>
    </main>

    <!-- 详情弹窗 -->
    <Teleport to="body">
      <div v-if="detail" class="modal-overlay" @click.self="detail = null">
        <div class="modal">
          <div class="modal-header">
            <h3>调用详情</h3>
            <button @click="detail = null" class="close-btn">&times;</button>
          </div>
          <pre class="detail-json">{{ JSON.stringify(detail, null, 2) }}</pre>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import type { CallRecord, Summary } from "./api";
import { fetchSummary, fetchCalls, fetchCallDetail } from "./api";
import StatsCards from "./components/StatsCards.vue";
import CallsTable from "./components/CallsTable.vue";

const summary = ref<Summary | null>(null);
const calls = ref<CallRecord[]>([]);
const total = ref(0);
const page = ref(1);
const size = ref(50);
const detail = ref<CallRecord | null>(null);

let timer: ReturnType<typeof setInterval>;

async function loadData() {
  summary.value = await fetchSummary();
  const result = await fetchCalls(page.value, size.value);
  calls.value = result.data;
  total.value = result.total;
}

function changePage(p: number) {
  page.value = p;
  loadData();
}

async function showDetail(id: string) {
  detail.value = await fetchCallDetail(id);
}

onMounted(() => {
  loadData();
  timer = setInterval(loadData, 10_000); // 10s 自动刷新
});

onUnmounted(() => clearInterval(timer));
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: #11111b;
  color: #cdd6f4;
}
.app { min-height: 100vh; }
.header {
  display: flex; align-items: center; gap: 12px;
  padding: 16px 24px;
  background: #1e1e2e;
  border-bottom: 1px solid #313244;
}
.header h1 { font-size: 20px; }
.version { font-size: 13px; color: #6c7086; }
.main { padding: 24px; max-width: 1400px; margin: 0 auto; }
.section { margin-bottom: 24px; }

.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.6);
  display: flex; align-items: center; justify-content: center;
  z-index: 100;
}
.modal {
  background: #1e1e2e; border: 1px solid #313244;
  border-radius: 8px; padding: 20px;
  max-width: 800px; max-height: 80vh; overflow: auto;
  width: 90%;
}
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.close-btn { background: none; border: none; color: #cdd6f4; font-size: 24px; cursor: pointer; }
.detail-json { font-size: 12px; color: #bac2de; white-space: pre-wrap; word-break: break-all; }
</style>
