<template>
  <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <template v-if="id === 'server'">
      <rect x="2" y="3" width="20" height="8" rx="2" />
      <rect x="2" y="13" width="20" height="8" rx="2" />
      <line x1="6" y1="7" x2="6.01" y2="7" />
      <line x1="6" y1="17" x2="6.01" y2="17" />
    </template>
    <template v-else-if="id === 'router'">
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
    </template>
    <template v-else-if="id === 'circuit-breaker'">
      <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
    </template>
    <template v-else-if="id === 'providers'">
      <path d="M4 7h16M4 12h16M4 17h10" />
      <circle cx="19" cy="17" r="2" />
    </template>
    <template v-else>
      <path d="M12 2L2 7l10 5 10-5-10-5z" />
      <path d="M2 17l10 5 10-5" />
      <path d="M2 12l10 5 10-5" />
    </template>
  </svg>
</template>

<script setup lang="ts">
defineProps<{
  id: string;
}>();
</script>

<style scoped>
.nav-icon {
  width: var(--sidebar-icon-size, 18px);
  height: var(--sidebar-icon-size, 18px);
  min-width: var(--sidebar-icon-size, 18px);
}
</style>
