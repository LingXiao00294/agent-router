<template>
  <div class="ui-card" :class="{ hoverable }">
    <div v-if="$slots.header || title" class="card-header">
      <slot name="header">
        <h3 class="card-title">{{ title }}</h3>
        <span v-if="subtitle" class="card-subtitle">{{ subtitle }}</span>
      </slot>
    </div>
    <div class="card-body" :class="{ 'no-padding': !bodyPadding }">
      <slot />
    </div>
    <div v-if="$slots.footer" class="card-footer">
      <slot name="footer" />
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string;
    subtitle?: string;
    hoverable?: boolean;
    bodyPadding?: boolean;
  }>(),
  {
    hoverable: false,
    bodyPadding: true,
  }
);
</script>

<style scoped>
.ui-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}
.ui-card.hoverable {
  transition: box-shadow var(--transition-fast), transform var(--transition-fast);
}
.ui-card.hoverable:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}

.card-header {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid var(--color-border);
}
.card-title {
  font-size: var(--text-md);
  font-weight: var(--font-semibold);
  color: var(--color-text-default);
  margin: 0;
}
.card-subtitle {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.card-body {
  padding: var(--space-5);
}
.card-body.no-padding {
  padding: 0;
}

.card-footer {
  padding: var(--space-3) var(--space-5);
  border-top: 1px solid var(--color-border);
  background: var(--color-surface-elevated);
}
</style>
