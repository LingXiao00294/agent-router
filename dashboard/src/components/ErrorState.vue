<template>
  <div class="error-state">
    <div class="error-icon">⚠</div>
    <h4 class="error-title">加载失败</h4>
    <p class="error-message">{{ message }}</p>
    <UiButton v-if="retry" variant="primary" @click="$emit('retry')">重试</UiButton>
  </div>
</template>

<script setup lang="ts">
import UiButton from "./ui/UiButton.vue";

defineProps<{
  message: string;
  retry?: boolean;
}>();

defineEmits<{
  retry: [];
}>();
</script>

<style scoped>
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-8) var(--space-5);
  text-align: center;
  color: var(--color-text-muted);
}
.error-icon {
  font-size: 40px;
  margin-bottom: var(--space-4);
}
.error-title {
  font-size: var(--text-md);
  font-weight: var(--font-semibold);
  color: var(--color-text-default);
  margin: 0 0 var(--space-2);
}
.error-message {
  font-size: var(--text-base);
  margin: 0 0 var(--space-5);
  max-width: 360px;
}
</style>
