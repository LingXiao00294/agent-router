<template>
  <CircuitBreakerPanel
    :states="configStore.circuitStates"
    :loading="configStore.circuitLoading"
    :error="configStore.circuitError"
    :resetting="configStore.resetting"
    @refresh="configStore.loadCircuitStates"
    @reset="resetCircuit"
  />
</template>

<script setup lang="ts">
import { useConfigStore } from "../../stores/config";
import { useToast } from "../../composables/useToast";
import CircuitBreakerPanel from "../../components/CircuitBreakerPanel.vue";

const configStore = useConfigStore();
const toast = useToast();

async function resetCircuit(provider: string) {
  try {
    await configStore.handleResetCircuitBreaker(provider);
    toast.success(`已重置 ${provider} 的熔断状态`);
  } catch {
    toast.error("重置失败");
  }
}
</script>
