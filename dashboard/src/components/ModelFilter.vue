<template>
  <div class="model-filter">
    <UiSelect
      ref="modelSelectRef"
      v-model="modelValue"
      label="模型"
      placeholder="全部模型"
      :options="modelOptions"
      clearable
    />
    <UiSelect
      v-model="statusValue"
      label="状态"
      placeholder="全部状态"
      :options="statusOptions"
      clearable
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import UiSelect from "./ui/UiSelect.vue";

const modelSelectRef = ref<InstanceType<typeof UiSelect> | null>(null);

const props = defineProps<{
  modelValue: string;
  statusValue: string;
  models: string[];
}>();

const emit = defineEmits<{
  "update:modelValue": [value: string];
  "update:statusValue": [value: string];
}>();

const modelOptions = computed(() =>
  props.models.map((m) => ({ label: m, value: m }))
);

const statusOptions = [
  { label: "成功", value: "success" },
  { label: "失败", value: "error" },
];

const modelValue = computed({
  get: () => props.modelValue,
  set: (v) => emit("update:modelValue", v),
});

const statusValue = computed({
  get: () => props.statusValue,
  set: (v) => emit("update:statusValue", v),
});

defineExpose({
  focus: () => modelSelectRef.value?.focus(),
});
</script>

<style scoped>
.model-filter {
  display: flex;
  gap: var(--space-4);
  align-items: flex-end;
}
</style>
