<template>
  <div
    class="ref-row"
    draggable="true"
    :class="{ dragging: isDragging, 'drag-over': isDragOver }"
    @dragstart="onDragStart"
    @dragover.prevent="onDragOver"
    @drop="onDrop"
    @dragend="onDragEnd"
  >
    <span class="drag-handle" title="拖动排序">⋮⋮</span>
    <span class="priority-badge">{{ refItem.priority }}</span>
    <UiSelect
      v-model="refItem.provider"
      class="ref-provider"
      placeholder="选择 provider"
      :options="providerOptions"
      :error="providerError"
      @blur="$emit('touch-provider')"
    />
    <UiInput
      v-model="refItem.model"
      class="ref-model"
      placeholder="真实模型名"
      :error="modelError"
      @blur="$emit('touch-model')"
    />
    <div class="ref-actions">
      <UiButton size="sm" variant="ghost" :disabled="!canMoveUp" @click="$emit('move-up')">▲</UiButton>
      <UiButton size="sm" variant="ghost" :disabled="!canMoveDown" @click="$emit('move-down')">▼</UiButton>
      <UiButton size="sm" variant="danger" @click="$emit('remove')">×</UiButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { ModelRef } from "../api";
import UiInput from "./ui/UiInput.vue";
import UiSelect from "./ui/UiSelect.vue";
import UiButton from "./ui/UiButton.vue";

const props = defineProps<{
  refItem: ModelRef;
  providerNames: string[];
  providerError?: string;
  modelError?: string;
  canMoveUp: boolean;
  canMoveDown: boolean;
}>();

const emit = defineEmits<{
  "move-up": [];
  "move-down": [];
  remove: [];
  "touch-provider": [];
  "touch-model": [];
  dragstart: [event: DragEvent];
  drop: [event: DragEvent];
}>();

const providerOptions = computed(() =>
  props.providerNames.map((name) => ({ label: name, value: name }))
);

const isDragging = ref(false);
const isDragOver = ref(false);

function onDragStart(e: DragEvent) {
  isDragging.value = true;
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = "move";
  }
  emit("dragstart", e);
}
function onDragOver(e: DragEvent) {
  isDragOver.value = true;
  if (e.dataTransfer) {
    e.dataTransfer.dropEffect = "move";
  }
}
function onDrop(e: DragEvent) {
  isDragOver.value = false;
  emit("drop", e);
}
function onDragEnd() {
  isDragging.value = false;
  isDragOver.value = false;
}
</script>

<style scoped>
.ref-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2);
  background: var(--color-surface-elevated);
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  margin-bottom: var(--space-2);
  transition: background var(--transition-fast), border-color var(--transition-fast);
}
.ref-row:hover {
  border-color: var(--color-border);
}
.ref-row.dragging {
  opacity: 0.4;
}
.ref-row.drag-over {
  border-color: var(--color-primary);
  background: var(--color-primary-muted);
}

.drag-handle {
  color: var(--color-text-muted);
  font-size: var(--text-md);
  cursor: grab;
  user-select: none;
  letter-spacing: 2px;
  padding: 0 var(--space-1);
}
.drag-handle:active {
  cursor: grabbing;
}
.priority-badge {
  background: var(--color-surface0);
  color: var(--color-text-muted);
  font-size: var(--text-xs);
  min-width: 22px;
  text-align: center;
  border-radius: var(--radius-sm);
  padding: 2px 4px;
}
.ref-provider {
  min-width: 140px;
}
.ref-model {
  flex: 1;
}
.ref-actions {
  display: flex;
  gap: var(--space-1);
}
</style>
