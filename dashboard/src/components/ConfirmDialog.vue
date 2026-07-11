<script setup lang="ts">
import { computed, ref } from "vue";
import { useConfirm } from "@/composables/useConfirm";
import { useOverlayChrome } from "@/composables/useOverlayChrome";

const { state, answer } = useConfirm();
const dialogRef = ref<HTMLElement | null>(null);
const open = computed(() => Boolean(state.value));
useOverlayChrome(open, dialogRef);
</script>

<template>
  <Teleport to="body">
    <div v-if="state" class="overlay" @click.self="answer(false)">
      <div
        ref="dialogRef"
        class="dialog panel"
        role="alertdialog"
        aria-modal="true"
        tabindex="-1"
      >
        <h3>{{ state.title }}</h3>
        <p>{{ state.message }}</p>
        <div class="actions">
          <button class="btn" type="button" @click="answer(false)">取消</button>
          <button
            class="btn"
            :class="state.danger ? 'btn-danger' : 'btn-primary'"
            type="button"
            @click="answer(true)"
          >
            {{ state.confirmText || "确认" }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  z-index: 1100;
  display: grid;
  place-items: center;
  background: rgba(10, 14, 20, 0.45);
  padding: 1rem;
}

.dialog {
  width: min(420px, 100%);
  padding: 1.25rem;
}

.dialog h3 {
  margin: 0 0 0.5rem;
  font-size: 1.05rem;
}

.dialog p {
  margin: 0 0 1.25rem;
  color: var(--text-secondary);
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
</style>
