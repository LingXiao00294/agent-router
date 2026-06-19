<template>
  <label class="ui-toggle" :class="{ checked: modelValue, disabled }">
    <input
      type="checkbox"
      :checked="modelValue"
      :disabled="disabled"
      @change="$emit('update:modelValue', ($event.target as HTMLInputElement).checked)"
    />
    <span class="toggle-track">
      <span class="toggle-thumb" />
    </span>
    <span v-if="label" class="toggle-label">{{ label }}</span>
  </label>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    modelValue: boolean;
    label?: string;
    disabled?: boolean;
  }>(),
  {
    label: "",
    disabled: false,
  }
);

defineEmits<{
  (e: "update:modelValue", value: boolean): void;
}>();
</script>

<style scoped>
.ui-toggle {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  cursor: pointer;
  user-select: none;
}
.ui-toggle input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}
.ui-toggle.disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.toggle-track {
  width: 36px;
  height: 20px;
  background: var(--color-surface1);
  border-radius: var(--radius-full);
  position: relative;
  transition: background var(--transition-fast);
}
.ui-toggle.checked .toggle-track {
  background: var(--color-primary);
}

.toggle-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  background: var(--color-text);
  border-radius: var(--radius-full);
  transition: transform var(--transition-fast);
}
.ui-toggle.checked .toggle-thumb {
  transform: translateX(16px);
}

.toggle-label {
  font-size: var(--text-base);
  color: var(--color-text-secondary);
}
</style>
