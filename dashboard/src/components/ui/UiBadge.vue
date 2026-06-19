<template>
  <span class="ui-badge" :class="[variant, size]">
    <slot />
  </span>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: "success" | "warning" | "error" | "info" | "neutral" | "primary";
    size?: "sm" | "md";
  }>(),
  {
    variant: "neutral",
    size: "md",
  }
);
</script>

<style scoped>
.ui-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-full);
  font-weight: var(--font-semibold);
  white-space: nowrap;
}
.ui-badge.sm {
  font-size: var(--text-xs);
  padding: 1px 6px;
}
.ui-badge.md {
  font-size: var(--text-sm);
  padding: 2px 8px;
}

.ui-badge.success {
  background: var(--color-success-muted);
  color: var(--color-success);
}
.ui-badge.warning {
  background: var(--color-warning-muted);
  color: var(--color-warning);
}
.ui-badge.error {
  background: var(--color-danger-muted);
  color: var(--color-danger);
}
.ui-badge.info {
  background: var(--color-info-muted);
  color: var(--color-info);
}
.ui-badge.neutral {
  background: var(--color-surface0);
  color: var(--color-text-secondary);
}
.ui-badge.primary {
  background: var(--color-primary-muted);
  color: var(--color-primary);
}
</style>
