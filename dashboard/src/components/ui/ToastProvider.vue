<template>
  <slot />
  <Teleport to="body">
    <div class="toast-provider" role="region" aria-label="通知">
      <UiToast
        v-for="toast in toasts"
        :key="toast.id"
        :message="toast.message"
        :type="toast.type"
        @close="removeToast(toast.id)"
      />
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { toasts, removeToast } from "../../composables/useToast";
import UiToast from "./UiToast.vue";
</script>

<style scoped>
.toast-provider {
  position: fixed;
  bottom: var(--space-5);
  right: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  z-index: var(--z-toast);
}

@media (max-width: 640px) {
  .toast-provider {
    right: 50%;
    transform: translateX(50%);
    align-items: center;
  }
}
</style>
