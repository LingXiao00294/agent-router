<template>
  <header class="page-header">
    <div class="header-left">
      <h1 class="page-title">{{ title }}</h1>
      <p v-if="subtitle" class="page-subtitle">{{ subtitle }}</p>
    </div>
    <div v-if="$slots.actions" class="header-actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup lang="ts">
defineProps<{
  title: string;
  subtitle?: string;
}>();
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-5);
}
.page-title {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--color-text-default);
  margin: 0;
}
.page-subtitle {
  font-size: var(--text-base);
  color: var(--color-text-muted);
  margin: var(--space-1) 0 0;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-shrink: 0;
}
</style>
