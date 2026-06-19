<template>
  <UiCard class="model-card" :body-padding="false">
    <template #header>
      <div class="model-header">
        <UiInput
          v-model="entry.name"
          label="虚拟模型名"
          placeholder="例如 opus-router"
          :error="nameError"
          @blur="touchName"
        />
        <UiButton size="sm" variant="danger" @click="$emit('remove')">删除</UiButton>
      </div>
    </template>

    <div class="model-body">
      <div class="refs-header">
        <span class="refs-title">Provider 链（按 priority 排序）</span>
        <UiButton size="sm" variant="secondary" @click="$emit('add-ref')">
          + 添加 Provider
        </UiButton>
      </div>

      <div v-if="entry.refs.length === 0" class="refs-empty">
        暂无 provider 映射
      </div>

      <RefRow
        v-for="(ref, idx) in entry.refs"
        :key="idx"
        :ref-item="ref"
        :provider-names="providerNames"
        :provider-error="providerError(idx)"
        :model-error="modelError(idx)"
        :can-move-up="idx > 0"
        :can-move-down="idx < entry.refs.length - 1"
        @move-up="$emit('move-ref', idx, idx - 1)"
        @move-down="$emit('move-ref', idx, idx + 1)"
        @remove="$emit('remove-ref', idx)"
        @touch-provider="touchProvider(idx)"
        @touch-model="touchModel(idx)"
        @dragstart="onRefDragStart(idx)"
        @drop="onRefDrop(idx)"
      />

      <p v-if="refsError" class="refs-error">{{ refsError }}</p>
    </div>
  </UiCard>
</template>

<script setup lang="ts">
import { ref } from "vue";
import type { ModelEntry } from "../stores/config";
import UiCard from "./ui/UiCard.vue";
import UiInput from "./ui/UiInput.vue";
import UiButton from "./ui/UiButton.vue";
import RefRow from "./RefRow.vue";

const props = defineProps<{
  entry: ModelEntry;
  providerNames: string[];
  nameError?: string;
  refsError?: string;
  providerErrors?: (string | undefined)[];
  modelErrors?: (string | undefined)[];
}>();

const emit = defineEmits<{
  remove: [];
  "add-ref": [];
  "remove-ref": [idx: number];
  "move-ref": [from: number, to: number];
  "touch-name": [];
  "touch-provider": [idx: number];
  "touch-model": [idx: number];
}>();

function providerError(idx: number): string | undefined {
  return props.providerErrors?.[idx];
}
function modelError(idx: number): string | undefined {
  return props.modelErrors?.[idx];
}
function touchName() {
  emit("touch-name");
}
function touchProvider(idx: number) {
  emit("touch-provider", idx);
}
function touchModel(idx: number) {
  emit("touch-model", idx);
}

// 拖拽排序：RefRow 内部已处理视觉反馈并 emit dragstart/drop，
// 这里记录被拖源行 index，drop 到目标行时触发 move-ref 重排。
const draggedIdx = ref<number | null>(null);

function onRefDragStart(idx: number) {
  draggedIdx.value = idx;
}
function onRefDrop(idx: number) {
  if (draggedIdx.value !== null && draggedIdx.value !== idx) {
    emit("move-ref", draggedIdx.value, idx);
  }
  draggedIdx.value = null;
}
</script>

<style scoped>
.model-card {
  margin-bottom: var(--space-3);
}
.model-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-4);
  width: 100%;
}
.model-header :deep(.ui-input-wrapper) {
  flex: 1;
}
.model-body {
  padding: var(--space-4);
}
.refs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}
.refs-title {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  font-weight: var(--font-medium);
}
.refs-empty {
  padding: var(--space-5);
  text-align: center;
  color: var(--color-text-muted);
  background: var(--color-surface-elevated);
  border-radius: var(--radius-md);
}
.refs-error {
  margin: var(--space-3) 0 0;
  font-size: var(--text-sm);
  color: var(--color-danger);
}
</style>
