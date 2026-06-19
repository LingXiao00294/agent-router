<template>
  <button
    :class="['ui-button', variant, size, { loading, block, disabled: isDisabled }]"
    :disabled="isDisabled"
    :type="type"
  >
    <UiSpinner v-if="loading" size="sm" class="btn-spinner" />
    <span v-else-if="$slots.icon" class="btn-icon"><slot name="icon" /></span>
    <span class="btn-label"><slot /></span>
  </button>
</template>

<script setup lang="ts">
import { computed } from "vue";
import UiSpinner from "./UiSpinner.vue";

const props = withDefaults(
  defineProps<{
    variant?: "primary" | "secondary" | "ghost" | "danger";
    size?: "sm" | "md" | "lg";
    loading?: boolean;
    disabled?: boolean;
    block?: boolean;
    type?: "button" | "submit" | "reset";
  }>(),
  {
    variant: "secondary",
    size: "md",
    loading: false,
    disabled: false,
    block: false,
    type: "button",
  }
);

const isDisabled = computed(() => props.loading || props.disabled);
</script>

<style scoped>
.ui-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  font-weight: var(--font-medium);
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.ui-button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.ui-button.sm {
  height: 26px;
  padding: 0 var(--space-3);
  font-size: var(--text-sm);
}
.ui-button.md {
  height: var(--button-height);
  padding: 0 var(--space-4);
  font-size: var(--text-base);
}
.ui-button.lg {
  height: 40px;
  padding: 0 var(--space-5);
  font-size: var(--text-md);
}

.ui-button.block {
  width: 100%;
}

.ui-button.primary {
  background: var(--color-button-primary-bg);
  color: var(--color-button-primary-text);
  border-color: var(--color-button-primary-bg);
}
.ui-button.primary:not(:disabled):hover {
  background: var(--color-button-primary-hover);
  border-color: var(--color-button-primary-hover);
}

.ui-button.secondary {
  background: var(--color-button-secondary-bg);
  color: var(--color-button-secondary-text);
  border-color: var(--color-border-strong);
}
.ui-button.secondary:not(:disabled):hover {
  background: var(--color-button-secondary-hover);
}

.ui-button.ghost {
  background: transparent;
  color: var(--color-button-ghost-text);
  border-color: transparent;
}
.ui-button.ghost:not(:disabled):hover {
  background: var(--color-button-ghost-hover);
}

.ui-button.danger {
  background: var(--color-danger-muted);
  color: var(--color-danger);
  border-color: var(--color-danger);
}
.ui-button.danger:not(:disabled):hover {
  background: var(--color-danger);
  color: var(--color-crust);
}

.btn-spinner {
  opacity: 0.8;
}
.btn-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
</style>
