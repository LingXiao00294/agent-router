<template>
  <div class="auto-refresh-control">
    <UiToggle v-model="enabled" label="自动刷新" />
    <UiSelect
      v-model="intervalModel"
      class="interval-select"
      :options="intervalOptions"
      placeholder="刷新间隔"
      :disabled="!enabled"
    />
    <span v-if="lastTick" class="last-tick">更新于 {{ formattedLastTick }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useAutoRefreshStore } from "../stores/autoRefresh";
import UiToggle from "./ui/UiToggle.vue";
import UiSelect from "./ui/UiSelect.vue";

const store = useAutoRefreshStore();

const enabled = computed({
  get: () => store.enabled,
  set: (v) => store.setEnabled(v),
});

const intervalModel = computed({
  get: () => String(store.intervalMs),
  set: (v) => store.setIntervalMs(Number(v)),
});

const intervalOptions = computed(() =>
  store.intervals.map((ms) => ({ label: `${ms / 1000}s`, value: String(ms) }))
);

const lastTick = computed(() => store.lastTick);
const formattedLastTick = computed(() => {
  if (!store.lastTick) return "";
  return new Date(store.lastTick).toLocaleTimeString();
});
</script>

<style scoped>
.auto-refresh-control {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}
.interval-select {
  width: 90px;
}
.last-tick {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}
</style>
