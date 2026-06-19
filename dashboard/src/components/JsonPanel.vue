<template>
  <div class="json-panel">
    <div class="json-header">
      <h4 class="section-title">{{ title }}</h4>
      <div class="json-actions">
        <UiButton size="sm" variant="ghost" @click="collapsed = !collapsed">
          {{ collapsed ? "展开" : "折叠" }}
        </UiButton>
        <UiButton size="sm" variant="ghost" @click="copy">{{ copied ? "已复制" : "复制" }}</UiButton>
      </div>
    </div>
    <pre v-if="!collapsed" class="code-block">{{ formatted }}</pre>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import UiButton from "./ui/UiButton.vue";

const props = defineProps<{
  title: string;
  raw: string | null;
}>();

const collapsed = ref(false);
const copied = ref(false);

const formatted = computed(() => {
  if (!props.raw) return "";
  try {
    const obj = JSON.parse(props.raw);
    if (obj.messages && Array.isArray(obj.messages)) {
      obj.messages = obj.messages.map((m: { content?: unknown }) => {
        if (typeof m.content === "string" && m.content.length > 500) {
          return { ...m, content: m.content.slice(0, 500) + "...[截断]" };
        }
        return m;
      });
    }
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(props.raw);
  }
});

async function copy() {
  try {
    await navigator.clipboard.writeText(formatted.value);
    copied.value = true;
    setTimeout(() => (copied.value = false), 1500);
  } catch {
    // ignore
  }
}
</script>

<style scoped>
.json-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.json-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}
.section-title {
  font-size: var(--text-md);
  font-weight: var(--font-semibold);
  color: var(--color-text-secondary);
  margin: 0;
}
.json-actions {
  display: flex;
  gap: var(--space-2);
}
.code-block {
  background: var(--color-crust);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 260px;
  overflow: auto;
  font-family: var(--font-mono);
}
</style>
