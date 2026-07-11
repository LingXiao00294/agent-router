<script setup lang="ts">
import { RouterLink } from "vue-router";
</script>

<template>
  <div class="page panel">
    <h1>404</h1>
    <p class="muted">页面不存在</p>
    <RouterLink class="btn btn-primary" to="/">返回 Overview</RouterLink>
  </div>
</template>

<style scoped>
.page {
  padding: 2rem;
  text-align: center;
  max-width: 420px;
  margin: 2rem auto;
}
h1 { margin: 0 0 0.5rem; }
p { margin: 0 0 1rem; }
</style>
