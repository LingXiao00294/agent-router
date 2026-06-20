<template>
  <div class="nav-group">
    <span class="nav-group-label sidebar-label">配置管理</span>
    <div class="nav-group-list" :class="{ 'is-dragging': !!draggedId }">
      <div
        v-for="(item, idx) in items"
        :key="item.id"
        class="nav-sub-item-wrap"
        :data-id="item.id"
        :class="{
          dragging: isDragging(item.id),
          'insert-before': dragOverState(idx) === 'before',
          'insert-after': dragOverState(idx) === 'after',
        }"
      >
        <span
          class="drag-handle"
          title="拖动排序"
          @pointerdown="onPointerDown(item.id, $event)"
        >
          ⋮⋮
        </span>
        <router-link :to="item.to" class="nav-item nav-sub-item" active-class="active" draggable="false">
          <ConfigNavIcon :id="item.id" />
          <span class="nav-text sidebar-label">{{ item.label }}</span>
        </router-link>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, toRef } from "vue";
import type { ConfigNavItemDef } from "../config/nav";
import { useAppStore } from "../stores/app";
import { useListDragReorder } from "../composables/useListDragReorder";
import ConfigNavIcon from "./ConfigNavIcon.vue";

const props = defineProps<{
  items: ConfigNavItemDef[];
}>();

const app = useAppStore();
const items = toRef(props, "items");

const { draggedId, onPointerDown, resetDragState, isDragging, dragOverState } = useListDragReorder({
  findIndex: (id) => items.value.findIndex((item) => item.id === id),
  reorder: (from, to) => app.reorderConfigNav(from, to),
});

onMounted(() => {
  resetDragState();
});

onUnmounted(() => {
  resetDragState();
});
</script>

<style scoped>
.nav-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin-top: var(--space-2);
  width: 100%;
}
.nav-group-label {
  display: block;
  padding: var(--space-2) var(--space-3) var(--space-1);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  overflow: hidden;
  transition:
    max-height var(--transition-base),
    padding var(--transition-base),
    opacity var(--transition-base);
}
.nav-group-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  width: 100%;
}
.nav-group-list.is-dragging {
  user-select: none;
}
.nav-group-list.is-dragging .nav-sub-item {
  pointer-events: none;
}
.nav-group-list.is-dragging .drag-handle {
  pointer-events: auto;
  cursor: grabbing;
}
.nav-sub-item-wrap {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  border-radius: var(--radius-md);
  position: relative;
}
.nav-sub-item-wrap.dragging {
  opacity: 0.55;
  z-index: 1;
}
.nav-sub-item-wrap.dragging .nav-sub-item {
  background: var(--color-surface-elevated);
  box-shadow: var(--shadow-md);
  transform: scale(1.02);
}
.nav-sub-item-wrap.insert-before::before,
.nav-sub-item-wrap.insert-after::after {
  content: "";
  position: absolute;
  left: var(--space-2);
  right: var(--space-2);
  height: 2px;
  border-radius: var(--radius-full);
  background: var(--color-primary);
  pointer-events: none;
}
.nav-sub-item-wrap.insert-before::before {
  top: -1px;
}
.nav-sub-item-wrap.insert-after::after {
  bottom: -1px;
}
.nav-sub-item {
  flex: 1;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  padding-left: var(--space-2);
  color: var(--color-text-muted);
  text-decoration: none;
  border-radius: var(--radius-md);
  transition:
    transform var(--transition-base),
    background var(--transition-fast),
    box-shadow var(--transition-fast),
    color var(--transition-fast);
}
.nav-sub-item:hover {
  background: var(--color-surface-hover);
  color: var(--color-text-default);
}
.nav-sub-item.active {
  background: var(--color-primary-muted);
  color: var(--color-primary);
}
.drag-handle {
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  cursor: grab;
  user-select: none;
  letter-spacing: 1px;
  padding: 0 var(--space-1);
  line-height: 1;
  flex-shrink: 0;
  width: 0;
  opacity: 0;
  overflow: hidden;
  touch-action: none;
  transition: opacity var(--transition-fast), width var(--transition-fast);
}
.nav-sub-item-wrap:hover .drag-handle,
.nav-group-list.is-dragging .drag-handle {
  width: auto;
  opacity: 1;
}
.drag-handle:hover {
  color: var(--color-text-default);
}
</style>

<style>
body.nav-drag-active {
  cursor: grabbing !important;
  user-select: none;
}
</style>
