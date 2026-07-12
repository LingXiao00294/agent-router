<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { storeToRefs } from "pinia";
import type { ModelRef } from "@/api/types";
import { useConfigStore } from "@/stores/config";
import { useConfirm } from "@/composables/useConfirm";

const store = useConfigStore();
const confirm = useConfirm();
const { draft, models, fieldErrors } = storeToRefs(store);
const newName = ref("");
const failoverEnabled = computed(() => draft.value?.router.mode === "failover");
const providerNames = computed(() => Object.keys(draft.value?.providers ?? {}));
const dragCandidate = ref<{
  model: string;
  index: number;
  pointerId: number;
  startX: number;
  startY: number;
  row: HTMLElement;
} | null>(null);
const draggingRef = ref<{
  model: string;
  index: number;
  pointerId: number;
  startX: number;
  startY: number;
  left: number;
  top: number;
  width: number;
} | null>(null);
const dropTarget = ref<{ model: string; index: number } | null>(null);
const dragPreview = ref<HTMLElement | null>(null);
const refKeys = new WeakMap<ModelRef, number>();
let nextRefKey = 0;
const DRAG_START_DISTANCE = 6;
type PriceField =
  | "input_price_per_million"
  | "output_price_per_million"
  | "cache_read_price_per_million"
  | "cache_write_price_per_million";
const priceFields: { key: PriceField; label: string }[] = [
  { key: "input_price_per_million", label: "输入" },
  { key: "output_price_per_million", label: "输出" },
  { key: "cache_read_price_per_million", label: "缓存读取" },
  { key: "cache_write_price_per_million", label: "缓存写入" },
];
const dragPreviewRow = computed(() => {
  const source = draggingRef.value;
  return source ? models.value[source.model]?.providers[source.index] ?? null : null;
});

watch(
  models,
  (current) => {
    for (const m of Object.values(current)) {
      const pinValid = m.providers.some(
        (row) => row.provider === m.pinned_provider && row.model === m.pinned_model,
      );
      if (pinValid) continue;
      const first = m.providers.find((row) => row.provider.trim() && row.model.trim());
      m.pinned_provider = first?.provider ?? null;
      m.pinned_model = first?.model ?? null;
    }
  },
  { deep: true, immediate: true },
);

function add() {
  store.addModel(newName.value.trim());
  newName.value = "";
}

async function remove(name: string) {
  const ok = await confirm.confirm({
    title: "删除虚拟模型",
    message: `确定删除「${name}」？`,
    confirmText: "删除",
    danger: true,
  });
  if (ok) store.removeModel(name);
}

function addRef(model: string) {
  const m = models.value[model];
  if (!m) return;
  const provider = providerNames.value[0] || "";
  m.providers.push({ provider, model: "", priority: m.providers.length + 1 });
}

function setPrice(row: ModelRef, field: PriceField, event: Event) {
  const raw = (event.target as HTMLInputElement).value;
  row[field] = raw === "" ? undefined : Number(raw);
}

function removeRef(model: string, idx: number) {
  const m = models.value[model];
  if (!m) return;
  m.providers.splice(idx, 1);
}

function refKey(row: ModelRef): number {
  let key = refKeys.get(row);
  if (key == null) {
    key = nextRefKey;
    nextRefKey += 1;
    refKeys.set(row, key);
  }
  return key;
}

function clearDragState() {
  dragCandidate.value = null;
  draggingRef.value = null;
  dropTarget.value = null;
}

function modelRows(model: string): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>("[data-ref-row]")).filter(
    (el) => el.dataset.refModel === model,
  );
}

function setDropTargetFromPointer(event: PointerEvent, model: string) {
  const rows = modelRows(model);
  if (!rows.length) {
    if (dropTarget.value) dropTarget.value = null;
    return;
  }
  const dragIndex =
    draggingRef.value && draggingRef.value.model === model ? draggingRef.value.index : -1;
  // Walk rows in DOM order (= array order) and find the first one whose vertical
  // midpoint falls below the pointer; the dragged item wants to sit just above it.
  let insertAt = rows.length;
  for (let i = 0; i < rows.length; i++) {
    const { top, height } = rows[i].getBoundingClientRect();
    if (event.clientY < top + height / 2) {
      insertAt = i;
      break;
    }
  }
  // Hide the indicator when the drop resolves to the item's own slot (no-op).
  if (dragIndex >= 0) {
    const destination = insertAt > dragIndex ? insertAt - 1 : insertAt;
    if (destination === dragIndex) {
      if (dropTarget.value) dropTarget.value = null;
      return;
    }
  }
  if (dropTarget.value?.model !== model || dropTarget.value.index !== insertAt) {
    dropTarget.value = { model, index: insertAt };
  }
}

/** FLIP: capture each row's vertical position before a reorder. */
function snapshotModelRows(model: string): Map<HTMLElement, number> {
  const tops = new Map<HTMLElement, number>();
  for (const el of modelRows(model)) tops.set(el, el.getBoundingClientRect().top);
  return tops;
}

/** FLIP: after the DOM settles into its new order, animate rows back from their old spots. */
function flipFromSnapshot(model: string, prev: Map<HTMLElement, number>) {
  const rows = modelRows(model);
  let touched = false;
  for (const el of rows) {
    const oldTop = prev.get(el);
    if (oldTop == null) continue;
    const dy = oldTop - el.getBoundingClientRect().top;
    if (dy === 0) continue;
    el.style.transition = "none";
    el.style.transform = `translateY(${dy}px)`;
    touched = true;
  }
  if (!touched) return;
  // Commit the inverted transforms, then release them so the stylesheet transition plays.
  void rows[0]?.offsetWidth;
  for (const el of rows) {
    if (el.style.transform) {
      el.style.transition = "";
      el.style.transform = "";
    }
  }
}

function moveDragPreview(clientX: number, clientY: number) {
  const source = draggingRef.value;
  const preview = dragPreview.value;
  if (!source || !preview) return;
  preview.style.transform = `translate3d(${clientX - source.startX}px, ${clientY - source.startY}px, 0) scale(1.02)`;
}

function startPointerDrag(event: PointerEvent, model: string, index: number) {
  if (event.button !== 0) return;
  const handle = event.currentTarget as HTMLElement;
  const row = handle.closest<HTMLElement>("[data-ref-row]");
  if (!row) return;
  handle.setPointerCapture(event.pointerId);
  dragCandidate.value = {
    model,
    index,
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    row,
  };
}

function movePointerDrag(event: PointerEvent) {
  const candidate = dragCandidate.value;
  if (!candidate || candidate.pointerId !== event.pointerId) return;

  if (!draggingRef.value) {
    const distance = Math.hypot(event.clientX - candidate.startX, event.clientY - candidate.startY);
    if (distance < DRAG_START_DISTANCE) return;
    const { left, top, width } = candidate.row.getBoundingClientRect();
    draggingRef.value = {
      model: candidate.model,
      index: candidate.index,
      pointerId: candidate.pointerId,
      startX: candidate.startX,
      startY: candidate.startY,
      left,
      top,
      width,
    };
    void nextTick(() => moveDragPreview(event.clientX, event.clientY));
  } else {
    moveDragPreview(event.clientX, event.clientY);
  }

  event.preventDefault();
  setDropTargetFromPointer(event, candidate.model);
}

function finishPointerDrag(event: PointerEvent) {
  const candidate = dragCandidate.value;
  const source = draggingRef.value;
  if (!candidate || candidate.pointerId !== event.pointerId) return;

  const target = source && dropTarget.value?.model === source.model ? dropTarget.value : null;
  if (source && target) {
    const insertAt = target.index;
    const destination = source.index < insertAt ? insertAt - 1 : insertAt;
    if (destination !== source.index) {
      // Snapshot before mutating so FLIP can animate every row into place.
      const snapshot = snapshotModelRows(source.model);
      store.moveRef(source.model, source.index, destination);
      void nextTick(() => flipFromSnapshot(source.model, snapshot));
    }
  }
  clearDragState();
}

function dragPreviewStyle(): Record<string, string> {
  const source = draggingRef.value;
  if (!source) return {};
  return {
    left: `${source.left}px`,
    top: `${source.top}px`,
    width: `${source.width}px`,
  };
}

function cancelPointerDrag(event: PointerEvent) {
  if (dragCandidate.value?.pointerId === event.pointerId) {
    clearDragState();
  }
}

function hasDropTarget(model: string, index: number, placement: "before" | "after"): boolean {
  const target = dropTarget.value;
  if (!target || target.model !== model) return false;
  return target.index === (placement === "before" ? index : index + 1);
}

function isDragging(model: string, index: number): boolean {
  return draggingRef.value?.model === model && draggingRef.value.index === index;
}

function isDropTarget(model: string, index: number, placement: "before" | "after"): boolean {
  return !isDragging(model, index) && hasDropTarget(model, index, placement);
}

function setPin(model: string, idx: number) {
  const m = models.value[model];
  if (!m) return;
  const ref = m.providers[idx];
  if (!ref) return;
  m.pinned_provider = ref.provider;
  m.pinned_model = ref.model;
}

function isPinned(model: string, idx: number) {
  const m = models.value[model];
  const ref = m?.providers[idx];
  if (!m || !ref) return false;
  return m.pinned_provider === ref.provider && m.pinned_model === ref.model;
}
</script>

<template>
  <section v-if="draft" class="wrap">
    <div class="toolbar panel">
      <div class="field grow">
        <label>新建虚拟模型</label>
        <input v-model="newName" placeholder="例如 opus-router" @keydown.enter="add" />
      </div>
      <button class="btn btn-primary" type="button" @click="add">添加</button>
    </div>
    <p v-if="fieldErrors.models" class="err">{{ fieldErrors.models }}</p>

    <article v-for="(m, name) in models" :key="name" class="panel card">
      <header class="card-head">
        <div>
          <h3 class="mono">{{ name }}</h3>
          <p class="muted tiny">
            拖动左侧手柄调整链顺序（priority）
            <template v-if="failoverEnabled"> · 失败时按顺序尝试</template>
            <template v-else> · 仅调用 Pin 指定的模型</template>
          </p>
          <p v-if="fieldErrors[`models.${name}`]" class="err">{{ fieldErrors[`models.${name}`] }}</p>
          <p v-if="fieldErrors[`models.${name}.pin`]" class="err">{{ fieldErrors[`models.${name}.pin`] }}</p>
        </div>
        <button class="btn btn-sm btn-danger" type="button" @click="remove(name)">删除</button>
      </header>

      <div v-if="!m.providers.length" class="empty-state">尚无 provider 引用</div>
      <div
        v-for="(row, idx) in m.providers"
        :key="refKey(row)"
        class="ref-row"
        data-ref-row
        :data-ref-model="name"
        :data-ref-index="idx"
        title="拖动调整优先级"
        :class="{
          'is-dragging': isDragging(name, idx),
          'drop-before': isDropTarget(name, idx, 'before'),
          'drop-after': isDropTarget(name, idx, 'after'),
        }"
      >
        <button
          class="drag-handle"
          type="button"
          aria-label="拖动调整优先级"
          title="拖动调整优先级"
          @pointerdown="startPointerDrag($event, name, idx)"
          @pointermove="movePointerDrag"
          @pointerup="finishPointerDrag"
          @pointercancel="cancelPointerDrag"
          @lostpointercapture="clearDragState"
        >
          ⠿
        </button>
        <span class="prio mono">#{{ idx + 1 }}</span>
        <select v-model="row.provider">
          <option disabled value="">选择 provider</option>
          <option v-for="pn in providerNames" :key="pn" :value="pn">{{ pn }}</option>
        </select>
        <input v-model="row.model" placeholder="上游模型名" />
        <div class="ref-actions">
          <button
            class="btn btn-sm"
            type="button"
            :class="{ 'btn-primary': isPinned(name, idx) }"
            title="设为指定模型"
            @click="setPin(name, idx)"
          >
            Pin
          </button>
          <button class="btn btn-sm btn-danger" type="button" @click="removeRef(name, idx)">×</button>
        </div>
        <div class="price-grid">
          <span class="price-title muted">费用（USD / 1M Token，可选）</span>
          <label v-for="price in priceFields" :key="price.key" class="price-field">
            <span>{{ price.label }}</span>
            <input
              type="number"
              min="0"
              step="0.0001"
              :value="row[price.key] ?? ''"
              placeholder="0"
              @input="setPrice(row, price.key, $event)"
            />
          </label>
        </div>
        <p v-if="fieldErrors[`models.${name}.ref.${idx}`]" class="err ref-err">
          {{ fieldErrors[`models.${name}.ref.${idx}`] }}
        </p>
        <p v-if="fieldErrors[`models.${name}.ref.${idx}.model`]" class="err ref-err">
          {{ fieldErrors[`models.${name}.ref.${idx}.model`] }}
        </p>
        <p v-if="fieldErrors[`models.${name}.ref.${idx}.price`]" class="err ref-err">
          {{ fieldErrors[`models.${name}.ref.${idx}.price`] }}
        </p>
      </div>

      <div class="card-foot">
        <button class="btn btn-sm" type="button" @click="addRef(name)">添加引用</button>
        <span v-if="m.pinned_provider" class="pin-summary muted">
          当前指定：{{ m.pinned_provider }}/{{ m.pinned_model }}
        </span>
      </div>
    </article>
  </section>

  <Teleport to="body">
    <div
      v-if="draggingRef && dragPreviewRow"
      ref="dragPreview"
      class="ref-row drag-preview"
      :style="dragPreviewStyle()"
      aria-hidden="true"
    >
      <button class="drag-handle" type="button" disabled>⠿</button>
      <span class="prio mono">#{{ draggingRef.index + 1 }}</span>
      <select :value="dragPreviewRow.provider" disabled>
        <option :value="dragPreviewRow.provider">{{ dragPreviewRow.provider }}</option>
      </select>
      <input :value="dragPreviewRow.model" readonly />
      <div class="ref-actions">
        <button
          class="btn btn-sm"
          type="button"
          :class="{ 'btn-primary': isPinned(draggingRef.model, draggingRef.index) }"
          disabled
        >
          Pin
        </button>
        <button class="btn btn-sm btn-danger" type="button" disabled>×</button>
      </div>
      <div class="price-grid">
        <span class="price-title muted">费用（USD / 1M Token，可选）</span>
        <label v-for="price in priceFields" :key="price.key" class="price-field">
          <span>{{ price.label }}</span>
          <input :value="dragPreviewRow[price.key] ?? ''" placeholder="0" readonly />
        </label>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.wrap { display: grid; gap: 0.85rem; }
.toolbar {
  display: flex;
  align-items: flex-end;
  gap: 0.75rem;
  padding: 0.9rem 1rem;
}
.grow { flex: 1; }
.card { padding: 1rem; }
.card-head {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.85rem;
}
.card-head h3 { margin: 0; }
.tiny { margin: 0.25rem 0 0; font-size: 0.8rem; }
.ref-row {
  display: grid;
  grid-template-columns: 28px 40px 140px 1fr auto;
  gap: 0.5rem;
  align-items: center;
  position: relative;
  min-height: 54px;
  margin-bottom: 0.65rem;
  padding: 0.6rem 0.7rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-elevated);
  transition:
    border-color 120ms ease,
    box-shadow 120ms ease,
    opacity 120ms ease,
    transform 200ms cubic-bezier(0.2, 0.8, 0.2, 1);
}
.drag-handle {
  border: 0;
  padding: 0.3rem 0.15rem;
  color: var(--text-muted);
  background: transparent;
  cursor: grab;
  font-size: 1.2rem;
  line-height: 1;
  touch-action: none;
}
.drag-handle:active { cursor: grabbing; }
.drag-handle:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
.ref-row.is-dragging {
  opacity: 0.35;
  border-style: dashed;
}
.drag-preview {
  position: fixed;
  z-index: 1000;
  margin: 0;
  pointer-events: none;
  box-shadow: 0 16px 32px rgba(15, 23, 42, 0.26);
  transform: scale(1.02);
  opacity: 0.7;
  transition: none;
}
.ref-row.drop-before::before,
.ref-row.drop-after::after {
  position: absolute;
  right: 0;
  left: 0;
  height: 3px;
  border-radius: 999px;
  background: var(--accent);
  box-shadow: 0 0 0 4px var(--accent-soft);
  content: "";
}
.ref-row.drop-before::before { top: -0.4rem; }
.ref-row.drop-after::after { bottom: -0.4rem; }
.ref-err {
  grid-column: 1 / -1;
  margin: 0;
}
.price-grid {
  display: grid;
  grid-column: 3 / -1;
  grid-template-columns: repeat(4, minmax(96px, 1fr));
  gap: 0.45rem;
  align-items: end;
}
.price-title {
  grid-column: 1 / -1;
  font-size: 0.72rem;
}
.price-field {
  display: grid;
  gap: 0.2rem;
  font-size: 0.72rem;
  color: var(--text-muted);
}
.price-field input {
  width: 100%;
}
.ref-row select,
.ref-row input {
  min-height: 34px;
  padding: 0.3rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-elevated);
}
.prio { color: var(--text-muted); font-size: 0.8rem; }
.ref-actions { display: flex; gap: 0.25rem; }
.card-foot {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.75rem;
}
.pin-summary { align-self: center; font-size: 0.78rem; }
.err { color: var(--danger); font-size: 0.78rem; margin: 0.25rem 0 0; }
@media (max-width: 800px) {
  .ref-row {
    grid-template-columns: 1fr;
  }
  .price-grid {
    grid-column: 1;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
