<template>
  <div class="not-found">
    <div class="code">404</div>
    <h1 class="title">页面未找到</h1>
    <p class="desc">你访问的页面不存在，请检查 URL 或返回首页。</p>
    <UiButton variant="primary" @click="$router.push('/')">返回仪表盘</UiButton>
  </div>
</template>

<script setup lang="ts">
import UiButton from "../components/ui/UiButton.vue";
</script>

<style scoped>
.not-found {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  text-align: center;
  color: var(--color-text-muted);
}
.code {
  font-size: 96px;
  font-weight: var(--font-bold);
  color: var(--color-primary);
  line-height: 1;
  margin-bottom: var(--space-4);
}
.title {
  font-size: var(--text-xl);
  color: var(--color-text-default);
  margin: 0 0 var(--space-3);
}
.desc {
  font-size: var(--text-base);
  margin: 0 0 var(--space-6);
  max-width: 360px;
}
</style>
