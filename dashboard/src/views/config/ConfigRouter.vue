<template>
  <ConfigSection title="Router">
    <div class="form-grid">
      <UiInput
        v-model.number="configStore.routerConfig.failure_threshold"
        label="熔断阈值（次连续失败）"
        type="number"
        :error="configStore.fieldError('router.failure_threshold')"
        @blur="touch('router.failure_threshold')"
      />
      <UiInput
        v-model.number="configStore.routerConfig.recovery_timeout"
        label="恢复超时（秒）"
        type="number"
        :error="configStore.fieldError('router.recovery_timeout')"
        @blur="touch('router.recovery_timeout')"
      />
    </div>
  </ConfigSection>
</template>

<script setup lang="ts">
import { useConfigStore } from "../../stores/config";
import ConfigSection from "../../components/ConfigSection.vue";
import UiInput from "../../components/ui/UiInput.vue";

const configStore = useConfigStore();

function touch(_path: string) {
  configStore.validate();
}
</script>

<style scoped>
.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-4);
}
</style>
