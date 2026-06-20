import { onScopeDispose, ref } from "vue";

export interface ListDragReorderOptions {
  findIndex: (id: string) => number;
  reorder: (from: number, to: number) => void;
  itemSelector?: string;
}

function computeMoveTarget(from: number, hover: number, insertAfter: boolean): number {
  let to = insertAfter ? hover + 1 : hover;
  if (from < to) to -= 1;
  return to;
}

export function useListDragReorder(options: ListDragReorderOptions) {
  const itemSelector = options.itemSelector ?? ".nav-sub-item-wrap";
  const draggedId = ref<string | null>(null);
  const dragOverIdx = ref<number | null>(null);
  const insertAfter = ref(false);

  let activePointerId: number | null = null;

  function resetDragState() {
    draggedId.value = null;
    dragOverIdx.value = null;
    insertAfter.value = false;
    activePointerId = null;
    document.body.classList.remove("nav-drag-active");
  }

  function findHoverTarget(clientX: number, clientY: number): { id: string; el: HTMLElement } | null {
    const el = document.elementFromPoint(clientX, clientY);
    const wrap = el?.closest(itemSelector) as HTMLElement | null;
    if (!wrap?.dataset.id) return null;
    return { id: wrap.dataset.id, el: wrap };
  }

  function updateHover(clientX: number, clientY: number) {
    if (!draggedId.value) return;

    const target = findHoverTarget(clientX, clientY);
    if (!target || target.id === draggedId.value) return;

    const hoverIdx = options.findIndex(target.id);
    if (hoverIdx === -1) return;

    const fromIdx = options.findIndex(draggedId.value);
    if (fromIdx === -1) return;

    const rect = target.el.getBoundingClientRect();
    const after = clientY >= rect.top + rect.height / 2;
    insertAfter.value = after;
    dragOverIdx.value = hoverIdx;

    const to = computeMoveTarget(fromIdx, hoverIdx, after);
    if (to !== fromIdx) {
      options.reorder(fromIdx, to);
    }
  }

  function onPointerMove(e: PointerEvent) {
    if (activePointerId !== e.pointerId) return;
    e.preventDefault();
    updateHover(e.clientX, e.clientY);
  }

  function onPointerUp(e: PointerEvent) {
    if (activePointerId !== e.pointerId) return;
    cleanupListeners();
    resetDragState();
  }

  function cleanupListeners() {
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
    window.removeEventListener("pointercancel", onPointerUp);
  }

  function onPointerDown(id: string, e: PointerEvent) {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();

    draggedId.value = id;
    dragOverIdx.value = null;
    insertAfter.value = false;
    activePointerId = e.pointerId;
    document.body.classList.add("nav-drag-active");

    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointercancel", onPointerUp);
  }

  function isDragging(id: string) {
    return draggedId.value === id;
  }

  function dragOverState(idx: number) {
    if (draggedId.value === null || dragOverIdx.value !== idx) {
      return null;
    }
    return insertAfter.value ? "after" : "before";
  }

  onScopeDispose(() => {
    cleanupListeners();
    resetDragState();
  });

  return {
    draggedId,
    dragOverIdx,
    insertAfter,
    onPointerDown,
    resetDragState,
    isDragging,
    dragOverState,
  };
}
