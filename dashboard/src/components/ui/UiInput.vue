<template>
  <div class="ui-input-wrapper" :class="{ inline, error: !!error }">
    <label v-if="label" :for="inputId" class="input-label">
      {{ label }}
      <span v-if="required" class="required">*</span>
    </label>
    <div class="input-container">
      <span v-if="$slots.prefix" class="input-prefix"><slot name="prefix" /></span>
      <input
        :id="inputId"
        v-bind="$attrs"
        :type="type"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        class="ui-input"
        @input="onInput"
        @blur="$emit('blur', $event)"
      />
      <button
        v-if="clearable && modelValue"
        type="button"
        class="input-clear"
        aria-label="清除"
        @click="$emit('update:modelValue', '')"
      >
        ×
      </button>
      <span v-if="$slots.suffix" class="input-suffix"><slot name="suffix" /></span>
    </div>
    <p v-if="error" class="input-error">{{ error }}</p>
    <p v-else-if="hint" class="input-hint">{{ hint }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

let idSeed = 0;

withDefaults(
  defineProps<{
    modelValue: string | number;
    label?: string;
    type?: string;
    placeholder?: string;
    disabled?: boolean;
    clearable?: boolean;
    required?: boolean;
    error?: string;
    hint?: string;
    inline?: boolean;
  }>(),
  {
    type: "text",
    placeholder: "",
    disabled: false,
    clearable: false,
    required: false,
    inline: false,
  }
);

const emit = defineEmits<{
  (e: "update:modelValue", value: string): void;
  (e: "blur", event: FocusEvent): void;
}>();

const inputId = computed(() => `ui-input-${++idSeed}`);

function onInput(event: Event) {
  emit("update:modelValue", (event.target as HTMLInputElement).value);
}
</script>

<style scoped>
.ui-input-wrapper {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.ui-input-wrapper.inline {
  flex-direction: row;
  align-items: center;
  gap: var(--space-3);
}

.input-label {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  font-weight: var(--font-medium);
}
.required {
  color: var(--color-danger);
  margin-left: var(--space-1);
}

.input-container {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  background: var(--color-input-bg);
  border: 1px solid var(--color-input-border);
  border-radius: var(--radius-md);
  padding: 0 var(--space-3);
  min-height: var(--input-height);
  transition: border-color var(--transition-fast);
}
.input-container:focus-within {
  border-color: var(--color-border-focus);
}
.ui-input-wrapper.error .input-container {
  border-color: var(--color-danger);
}

.ui-input {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--color-text-default);
  font-size: var(--text-base);
  min-height: var(--input-height);
  width: 100%;
}
.ui-input:focus {
  outline: none;
}
.ui-input::placeholder {
  color: var(--color-input-placeholder);
}
.ui-input:disabled {
  color: var(--color-text-disabled);
  cursor: not-allowed;
}

.input-prefix,
.input-suffix {
  display: inline-flex;
  align-items: center;
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

.input-clear {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: var(--radius-full);
  border: none;
  background: var(--color-surface1);
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: var(--text-sm);
  line-height: 1;
}
.input-clear:hover {
  background: var(--color-danger);
  color: var(--color-crust);
}

.input-error {
  font-size: var(--text-sm);
  color: var(--color-danger);
  margin: 0;
}
.input-hint {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  margin: 0;
}
</style>
