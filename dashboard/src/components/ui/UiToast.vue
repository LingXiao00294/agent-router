<template>
  <div class="toast-item" :class="type" role="status" aria-live="polite">
    <span class="toast-icon">{{ icon }}</span>
    <span class="toast-message">{{ message }}</span>
    <button class="toast-close" aria-label="关闭" @click="emit('close')">×</button>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { ToastType } from "../../composables/useToast";

const props = defineProps<{
  message: string;
  type: ToastType;
}>();

const emit = defineEmits<{
  (e: "close"): void;
}>();

const icon = computed(() => {
  switch (props.type) {
    case "success":
      return "✓";
    case "error":
      return "✕";
    case "warning":
      return "!";
    default:
      return "ℹ";
  }
});
</script>

<style scoped>
.toast-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-width: 220px;
  max-width: 360px;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text-default);
  animation: slide-in var(--transition-base) ease;
}
.toast-item.success {
  border-left: 3px solid var(--color-success);
}
.toast-item.error {
  border-left: 3px solid var(--color-danger);
}
.toast-item.warning {
  border-left: 3px solid var(--color-warning);
}
.toast-item.info {
  border-left: 3px solid var(--color-info);
}

.toast-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: var(--radius-full);
  font-weight: var(--font-bold);
  font-size: var(--text-sm);
}
.toast-item.success .toast-icon {
  background: var(--color-success-muted);
  color: var(--color-success);
}
.toast-item.error .toast-icon {
  background: var(--color-danger-muted);
  color: var(--color-danger);
}
.toast-item.warning .toast-icon {
  background: var(--color-warning-muted);
  color: var(--color-warning);
}
.toast-item.info .toast-icon {
  background: var(--color-info-muted);
  color: var(--color-info);
}

.toast-message {
  flex: 1;
  font-size: var(--text-base);
}

.toast-close {
  background: transparent;
  border: none;
  color: var(--color-text-muted);
  font-size: 18px;
  cursor: pointer;
  line-height: 1;
  padding: var(--space-1);
  border-radius: var(--radius-sm);
}
.toast-close:hover {
  background: var(--color-surface0);
  color: var(--color-text-default);
}

@keyframes slide-in {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}
</style>
