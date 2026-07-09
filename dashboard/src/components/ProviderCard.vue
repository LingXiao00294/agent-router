<template>
  <UiCard class="provider-card" :body-padding="false">
    <template #header>
      <div class="provider-header">
        <UiInput
          v-model="entry.name"
          label="名称"
          placeholder="provider 名称"
          :error="nameError"
          @blur="touchName"
        />
        <div class="provider-actions">
          <UiButton size="sm" variant="ghost" @click="collapsed = !collapsed">
            {{ collapsed ? "展开" : "折叠" }}
          </UiButton>
          <UiButton size="sm" variant="danger" @click="$emit('remove')">删除</UiButton>
        </div>
      </div>
    </template>

    <div v-show="!collapsed" class="provider-body">
      <div class="provider-fields">
        <UiSelect
          v-model="entry.type"
          label="类型"
          :options="['anthropic', 'openai']"
        />
        <UiInput
          v-model="entry.api_key"
          label="API Key"
          type="password"
          :placeholder="entry.has_key ? '留空则保留当前 key' : 'sk-...'"
        />
        <UiInput v-model="entry.base_url" label="Base URL" placeholder="https://api.anthropic.com" />
        <UiInput
          v-model.number="entry.timeout_seconds"
          label="超时（秒）"
          type="number"
          :error="timeoutError"
          @blur="touchTimeout"
        />
        <UiInput
          :model-value="entry.failure_threshold ?? ''"
          label="熔断阈值（可选）"
          type="number"
          placeholder="默认"
          @update:model-value="(v) => (entry.failure_threshold = v === '' ? null : Number(v))"
        />
        <UiInput
          :model-value="entry.recovery_timeout ?? ''"
          label="恢复超时（可选）"
          type="number"
          placeholder="默认"
          @update:model-value="(v) => (entry.recovery_timeout = v === '' ? null : Number(v))"
        />
        <UiInput
          v-model.number="entry.max_concurrent"
          label="最大并发（0=不限）"
          type="number"
        />
        <UiInput
          v-model.number="entry.max_queue"
          label="排队上限（0=不排）"
          type="number"
        />
        <UiInput
          v-model.number="entry.queue_wait_timeout"
          label="排队等待超时（秒）"
          type="number"
        />
        <UiInput
          v-model.number="entry.rate_limit_cooldown"
          label="限流冷却（秒）"
          type="number"
        />
      </div>
    </div>
  </UiCard>
</template>

<script setup lang="ts">
import { ref } from "vue";
import type { ProviderEntry } from "../stores/config";
import UiCard from "./ui/UiCard.vue";
import UiInput from "./ui/UiInput.vue";
import UiSelect from "./ui/UiSelect.vue";
import UiButton from "./ui/UiButton.vue";

defineProps<{
  entry: ProviderEntry;
  nameError?: string;
  timeoutError?: string;
}>();

const emit = defineEmits<{
  remove: [];
  "touch-name": [];
  "touch-timeout": [];
}>();

const collapsed = ref(false);

const touchName = () => emit("touch-name");
const touchTimeout = () => emit("touch-timeout");
</script>

<style scoped>
.provider-card {
  margin-bottom: var(--space-3);
}
.provider-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  width: 100%;
}
.provider-header :deep(.ui-input-wrapper) {
  flex: 1;
}
.provider-actions {
  display: flex;
  gap: var(--space-2);
  flex-shrink: 0;
  padding-top: 20px;
}
.provider-body {
  padding: var(--space-4);
}
.provider-fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-4);
}
</style>
