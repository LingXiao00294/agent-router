<template>
  <span class="ui-spinner" :class="size" aria-label="加载中" />
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    size?: "xs" | "sm" | "md" | "lg";
  }>(),
  {
    size: "md",
  }
);
</script>

<style scoped>
.ui-spinner {
  display: inline-block;
  border: 2px solid var(--color-surface1);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
.ui-spinner.xs {
  width: 12px;
  height: 12px;
}
.ui-spinner.sm {
  width: 16px;
  height: 16px;
}
.ui-spinner.md {
  width: 24px;
  height: 24px;
}
.ui-spinner.lg {
  width: 32px;
  height: 32px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
