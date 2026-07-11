<script setup lang="ts">
import { onMounted, ref } from "vue";
import { storeToRefs } from "pinia";
import * as api from "@/api";
import { useAppStore } from "@/stores/app";
import { useToast } from "@/composables/useToast";

const app = useAppStore();
const toast = useToast();
const { circuit } = storeToRefs(app);
const loadError = ref<string | null>(null);
const loading = ref(false);

async function refresh() {
  loading.value = true;
  loadError.value = null;
  try {
    await app.loadCircuit();
  } catch (err) {
    loadError.value =
      err instanceof Error ? err.message : "加载熔断状态失败";
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void refresh();
});

async function reset(name: string) {
  try {
    await api.resetCircuitBreaker(name);
    toast.success(`已重置 ${name}`);
    await refresh();
  } catch (err) {
    toast.error(err instanceof Error ? err.message : "重置失败");
  }
}

function badgeClass(state: string) {
  if (state === "closed") return "badge-success";
  if (state === "open") return "badge-danger";
  return "badge-warn";
}
</script>

<template>
  <section class="panel">
    <header class="head">
      <h2 class="panel-title">Circuit Breaker</h2>
      <button class="btn btn-sm" type="button" :disabled="loading" @click="refresh">
        {{ loading ? "加载中…" : "刷新" }}
      </button>
    </header>
    <div v-if="loadError" class="error-state">{{ loadError }}</div>
    <div v-else-if="loading && !Object.keys(circuit).length" class="empty-state">
      加载中…
    </div>
    <div v-else-if="!Object.keys(circuit).length" class="empty-state">
      暂无 provider 熔断状态
    </div>
    <div v-else class="table-wrap">
      <table class="data">
        <thead>
          <tr>
            <th>Provider</th>
            <th>状态</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(state, name) in circuit" :key="name">
            <td class="mono">{{ name }}</td>
            <td>
              <span class="badge" :class="badgeClass(state)">{{ state }}</span>
            </td>
            <td>
              <button
                v-if="state !== 'closed'"
                class="btn btn-sm"
                type="button"
                @click="reset(name)"
              >
                Reset
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.panel { padding: 1rem; }
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
}
table.data tbody tr { cursor: default; }
</style>
