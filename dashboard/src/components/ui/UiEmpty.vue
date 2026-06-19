<template>
  <div class="ui-empty">
    <div class="empty-icon">
      <slot name="icon">📭</slot>
    </div>
    <h4 class="empty-title">{{ title }}</h4>
    <p v-if="description" class="empty-desc">{{ description }}</p>
    <div v-if="$slots.action" class="empty-action">
      <slot name="action" />
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string;
    description?: string;
  }>(),
  {
    title: "暂无数据",
    description: "",
  }
);
</script>

<style scoped>
.ui-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-8) var(--space-5);
  color: var(--color-text-muted);
  text-align: center;
}
.empty-icon {
  font-size: 32px;
  margin-bottom: var(--space-4);
  opacity: 0.7;
}
.empty-title {
  font-size: var(--text-md);
  font-weight: var(--font-semibold);
  color: var(--color-text-secondary);
  margin: 0 0 var(--space-2);
}
.empty-desc {
  font-size: var(--text-base);
  margin: 0 0 var(--space-4);
  max-width: 320px;
}
.empty-action {
  margin-top: var(--space-2);
}
</style>
