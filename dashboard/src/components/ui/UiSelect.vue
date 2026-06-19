<template>
  <div class="ui-select-wrapper" :class="{ inline, error: !!error }">
    <label v-if="label" :for="selectId" class="select-label">
      {{ label }}
      <span v-if="required" class="required">*</span>
    </label>
    <div class="select-container">
      <select
        :id="selectId"
        ref="selectRef"
        :value="modelValue"
        :disabled="disabled"
        class="ui-select"
        @change="onChange"
      >
        <option v-if="placeholder" value="" disabled>{{ placeholder }}</option>
        <option
          v-for="opt in normalizedOptions"
          :key="String(opt.value)"
          :value="opt.value"
        >
          {{ opt.label }}
        </option>
      </select>
      <button
        v-if="clearable && hasValue"
        type="button"
        class="select-clear"
        aria-label="清除"
        @click="clear"
      >
        ×
      </button>
      <span class="select-arrow">▼</span>
    </div>
    <p v-if="error" class="select-error">{{ error }}</p>
    <p v-else-if="hint" class="select-hint">{{ hint }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";

let idSeed = 0;

export interface SelectOption {
  label: string;
  value: string | number;
}

const selectRef = ref<HTMLSelectElement | null>(null);
const props = withDefaults(
  defineProps<{
    modelValue: string | number;
    options: (string | SelectOption)[];
    label?: string;
    placeholder?: string;
    disabled?: boolean;
    required?: boolean;
    error?: string;
    hint?: string;
    inline?: boolean;
    clearable?: boolean;
  }>(),
  {
    placeholder: "请选择",
    disabled: false,
    required: false,
    inline: false,
    clearable: false,
  }
);

const emit = defineEmits<{
  (e: "update:modelValue", value: string): void;
}>();

const selectId = `ui-select-${++idSeed}`;

const normalizedOptions = computed<SelectOption[]>(() =>
  props.options.map((o) =>
    typeof o === "string" ? { label: o, value: o } : o
  )
);

const hasValue = computed(() => props.modelValue !== "" && props.modelValue != null);

function clear() {
  emit("update:modelValue", "");
}

function onChange(event: Event) {
  emit("update:modelValue", (event.target as HTMLSelectElement).value);
}

defineExpose({
  focus: () => selectRef.value?.focus(),
});
</script>

<style scoped>
.ui-select-wrapper {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.ui-select-wrapper.inline {
  flex-direction: row;
  align-items: center;
  gap: var(--space-3);
}

.select-label {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  font-weight: var(--font-medium);
}
.required {
  color: var(--color-danger);
  margin-left: var(--space-1);
}

.select-container {
  position: relative;
  display: flex;
  align-items: center;
}

.ui-select {
  appearance: none;
  width: 100%;
  background: var(--color-input-bg);
  border: 1px solid var(--color-input-border);
  border-radius: var(--radius-md);
  color: var(--color-text-default);
  font-size: var(--text-base);
  min-height: var(--input-height);
  padding: 0 var(--space-7) 0 var(--space-3);
  cursor: pointer;
  transition: border-color var(--transition-fast);
}
.ui-select:focus {
  outline: none;
  border-color: var(--color-border-focus);
}
.ui-select:disabled {
  color: var(--color-text-disabled);
  cursor: not-allowed;
}
.ui-select-wrapper.error .ui-select {
  border-color: var(--color-danger);
}

.select-arrow {
  position: absolute;
  right: var(--space-3);
  pointer-events: none;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.select-clear {
  position: absolute;
  right: var(--space-7);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border: none;
  border-radius: var(--radius-full);
  background: var(--color-surface1);
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: var(--text-sm);
  line-height: 1;
}
.select-clear:hover {
  background: var(--color-danger);
  color: var(--color-crust);
}

.select-error {
  font-size: var(--text-sm);
  color: var(--color-danger);
  margin: 0;
}
.select-hint {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  margin: 0;
}
</style>
