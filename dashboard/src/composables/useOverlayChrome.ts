import {
  onScopeDispose,
  watch,
  type MaybeRefOrGetter,
  type Ref,
  toValue,
} from "vue";

const overlayStack: symbol[] = [];
let bodyLockCount = 0;
let savedBodyOverflow = "";

/**
 * Lock body scroll and trap Tab focus inside `root` while `active` is true.
 * Restores previously focused element on release.
 */
export function useOverlayChrome(
  active: MaybeRefOrGetter<boolean>,
  root: Ref<HTMLElement | null>,
) {
  let previousFocus: HTMLElement | null = null;
  let locked = false;
  const overlayId = Symbol("overlay");

  function focusables(el: HTMLElement): HTMLElement[] {
    return [
      ...el.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
    ].filter((node) => !node.hasAttribute("disabled") && node.offsetParent !== null);
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key !== "Tab" || !root.value || overlayStack.at(-1) !== overlayId) return;
    const nodes = focusables(root.value);
    if (!nodes.length) return;
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    const current = document.activeElement as HTMLElement | null;
    if (e.shiftKey) {
      if (current === first || !root.value.contains(current)) {
        e.preventDefault();
        last.focus();
      }
    } else if (current === last) {
      e.preventDefault();
      first.focus();
    }
  }

  function lock() {
    if (locked) return;
    locked = true;
    previousFocus = document.activeElement as HTMLElement | null;
    overlayStack.push(overlayId);
    if (bodyLockCount === 0) {
      savedBodyOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
    }
    bodyLockCount += 1;
    window.addEventListener("keydown", onKeydown);
    requestAnimationFrame(() => {
      const el = root.value;
      if (!el) return;
      const nodes = focusables(el);
      (nodes[0] ?? el).focus();
    });
  }

  function unlock() {
    if (!locked) return;
    locked = false;
    const wasTopOverlay = overlayStack.at(-1) === overlayId;
    const index = overlayStack.lastIndexOf(overlayId);
    if (index !== -1) overlayStack.splice(index, 1);
    window.removeEventListener("keydown", onKeydown);
    bodyLockCount = Math.max(0, bodyLockCount - 1);
    if (bodyLockCount === 0) {
      document.body.style.overflow = savedBodyOverflow;
      savedBodyOverflow = "";
    }
    if (wasTopOverlay) previousFocus?.focus?.();
    previousFocus = null;
  }

  watch(
    () => toValue(active),
    (on) => {
      if (on) lock();
      else unlock();
    },
    { immediate: true },
  );

  onScopeDispose(() => {
    unlock();
  });
}
