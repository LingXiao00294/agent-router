<template>
  <UiModal
    :open="!!state"
    :title="state?.title"
    size="sm"
    :closable="false"
    @close="onCancel"
  >
    <p>{{ state?.message }}</p>
    <template #footer>
      <UiButton variant="ghost" @click="onCancel">{{ state?.cancelText }}</UiButton>
      <UiButton :variant="confirmVariant" @click="onConfirm">{{ state?.confirmText }}</UiButton>
    </template>
  </UiModal>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { activeConfirm, resolveConfirm } from "../../composables/useConfirm";
import UiModal from "./UiModal.vue";
import UiButton from "./UiButton.vue";

const state = computed(() => activeConfirm.value);
const confirmVariant = computed(() =>
  state.value?.variant === "danger" ? "danger" : "primary"
);

function onConfirm() {
  resolveConfirm(true);
}

function onCancel() {
  resolveConfirm(false);
}
</script>
