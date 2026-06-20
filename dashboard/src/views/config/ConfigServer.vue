<template>
  <ConfigSection title="Server">
    <div class="form-grid">
      <UiInput v-model="configStore.serverConfig.host" label="Host" />
      <UiInput
        v-model.number="configStore.serverConfig.port"
        label="端口"
        type="number"
        :error="configStore.fieldError('server.port')"
        @blur="touch('server.port')"
      />
      <UiSelect
        v-model="configStore.serverConfig.log_level"
        label="日志级别"
        :options="['debug', 'info', 'warning', 'error']"
      />
      <UiInput
        v-model="configStore.serverConfig.log_file"
        label="日志文件"
        hint="留空则只输出到 stdout"
      />
      <UiInput
        v-model.number="configStore.serverConfig.log_max_bytes"
        label="日志大小限制（字节）"
        type="number"
      />
      <UiInput
        v-model.number="configStore.serverConfig.log_backup_count"
        label="日志备份数"
        type="number"
      />
    </div>
  </ConfigSection>
</template>

<script setup lang="ts">
import { useConfigStore } from "../../stores/config";
import ConfigSection from "../../components/ConfigSection.vue";
import UiInput from "../../components/ui/UiInput.vue";
import UiSelect from "../../components/ui/UiSelect.vue";

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
