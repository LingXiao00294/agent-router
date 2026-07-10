<script setup lang="ts">
import { onMounted } from "vue";
import { storeToRefs } from "pinia";
import * as api from "@/api";
import { useAppStore } from "@/stores/app";
import { useToast } from "@/composables/useToast";

const app = useAppStore();
const toast = useToast();
const { circuit } = storeToRefs(app);

onMounted(() => {
  void app.loadCircuit();
});

async function reset(name: string) {
  try {
    await api.resetCircuitBreaker(name);
    toast.success(`已重置 ${name}`);
    await app.loadCircuit();
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
      <button class="btn btn-sm" type="button" @click="app.loadCircuit()">刷新</button>
    </header>
    <div v-if="!Object.keys(circuit).length" class="empty-state">暂无 provider 熔断状态</div>
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
