<template>
  <div class="ui-skeleton" :class="[variant, { rounded, pulse }]">
    <slot />
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: "text" | "rect" | "circle";
    rounded?: boolean;
    pulse?: boolean;
  }>(),
  {
    variant: "text",
    rounded: true,
    pulse: true,
  }
);
</script>

<style scoped>
.ui-skeleton {
  background: linear-gradient(
    90deg,
    var(--color-surface0) 25%,
    var(--color-surface1) 50%,
    var(--color-surface0) 75%
  );
  background-size: 200% 100%;
  display: inline-block;
}
.ui-skeleton.rounded {
  border-radius: var(--radius-md);
}
.ui-skeleton.text {
  height: 1em;
  width: 100%;
}
.ui-skeleton.rect {
  width: 100%;
}
.ui-skeleton.circle {
  border-radius: var(--radius-full);
  aspect-ratio: 1 / 1;
}
.ui-skeleton.pulse {
  animation: skeleton-pulse 1.5s infinite linear;
}

@keyframes skeleton-pulse {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}
</style>
