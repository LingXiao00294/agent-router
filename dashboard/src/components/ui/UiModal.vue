<template>
  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="open"
        ref="backdropRef"
        class="modal-backdrop"
        role="dialog"
        aria-modal="true"
        tabindex="-1"
        @click.self="onBackdropClick"
        @keydown="onKeydown"
      >
        <div ref="containerRef" class="modal-container" :class="size">
          <div class="modal-header">
            <h3 class="modal-title">{{ title }}</h3>
            <button
              v-if="closable"
              ref="closeRef"
              type="button"
              class="modal-close"
              aria-label="关闭"
              @click="close"
            >
              ×
            </button>
          </div>
          <div class="modal-body">
            <slot />
          </div>
          <div v-if="$slots.footer" class="modal-footer">
            <slot name="footer" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from "vue";

const props = withDefaults(
  defineProps<{
    open: boolean;
    title?: string;
    size?: "sm" | "md" | "lg" | "xl";
    closable?: boolean;
    closeOnBackdrop?: boolean;
  }>(),
  {
    title: "",
    size: "md",
    closable: true,
    closeOnBackdrop: true,
  }
);

const emit = defineEmits<{
  (e: "close"): void;
}>();

const backdropRef = ref<HTMLElement | null>(null);
const containerRef = ref<HTMLElement | null>(null);
const closeRef = ref<HTMLElement | null>(null);
let previouslyFocused: Element | null = null;

function close() {
  emit("close");
}

function onBackdropClick() {
  if (props.closeOnBackdrop) close();
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") {
    e.stopPropagation();
    close();
  } else if (e.key === "Tab") {
    trapFocus(e);
  }
}

function trapFocus(e: KeyboardEvent) {
  if (!containerRef.value) return;
  const focusable = containerRef.value.querySelectorAll<HTMLElement>(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  );
  if (focusable.length === 0) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first.focus();
  }
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      previouslyFocused = document.activeElement;
      void nextTick(() => {
        closeRef.value?.focus();
      });
    } else {
      if (previouslyFocused instanceof HTMLElement) {
        previouslyFocused.focus();
      }
    }
  }
);
</script>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal-backdrop);
  padding: var(--space-5);
}
.modal-backdrop:focus {
  outline: none;
}

.modal-container {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
  width: 100%;
  max-height: calc(100vh - var(--space-7) * 2);
  display: flex;
  flex-direction: column;
  z-index: var(--z-modal);
}
.modal-container.sm {
  max-width: 400px;
}
.modal-container.md {
  max-width: 560px;
}
.modal-container.lg {
  max-width: 760px;
}
.modal-container.xl {
  max-width: 960px;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid var(--color-border);
}
.modal-title {
  font-size: var(--text-md);
  font-weight: var(--font-semibold);
  margin: 0;
  color: var(--color-text-default);
}
.modal-close {
  background: transparent;
  border: none;
  color: var(--color-text-muted);
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
  padding: var(--space-1);
  border-radius: var(--radius-md);
}
.modal-close:hover {
  background: var(--color-surface0);
  color: var(--color-text-default);
}

.modal-body {
  padding: var(--space-5);
  overflow-y: auto;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-5);
  border-top: 1px solid var(--color-border);
  background: var(--color-surface-elevated);
}

.modal-enter-active,
.modal-leave-active {
  transition: opacity var(--transition-base);
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
</style>
