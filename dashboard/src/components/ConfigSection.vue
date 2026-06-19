<template>
  <section class="config-section">
    <div class="section-header">
      <div class="section-titles">
        <h3 class="section-title">{{ title }}</h3>
        <p v-if="subtitle" class="section-subtitle">{{ subtitle }}</p>
      </div>
      <div v-if="$slots.actions" class="section-actions">
        <slot name="actions" />
      </div>
    </div>
    <div class="section-body">
      <slot />
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  title: string;
  subtitle?: string;
}>();
</script>

<style scoped>
.config-section {
  margin-bottom: var(--space-7);
}
.section-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
}
.section-titles {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.section-title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text-default);
  margin: 0;
}
.section-subtitle {
  font-size: var(--text-base);
  color: var(--color-text-muted);
  margin: 0;
}
.section-actions {
  display: flex;
  gap: var(--space-3);
  flex-shrink: 0;
}
.section-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
</style>
