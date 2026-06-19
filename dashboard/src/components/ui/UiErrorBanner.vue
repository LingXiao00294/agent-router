<template>
  <div class="ui-error-banner" role="alert">
    <span class="error-icon">⚠</span>
    <span class="error-message">{{ message }}</span>
    <UiButton v-if="retry" size="sm" variant="ghost" @click="$emit('retry')">
      重试
    </UiButton>
  </div>
</template>

<script setup lang="ts">
import UiButton from "./UiButton.vue";

defineProps<{
  message: string;
  retry?: boolean;
}>();

defineEmits<{
  (e: "retry"): void;
}>();
</script>

<style scoped>
.ui-error-banner {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--color-danger-muted);
  border: 1px solid var(--color-danger);
  border-radius: var(--radius-md);
  color: var(--color-danger);
}
.error-icon {
  font-size: var(--text-md);
}
.error-message {
  flex: 1;
  font-size: var(--text-base);
}
</style>
