import { computed, onScopeDispose, ref } from "vue";
import { useMediaQuery } from "@vueuse/core";
import { useLocalStorageState } from "./useLocalStorageState";

const SIDEBAR_EXPANDED = "var(--sidebar-width)";
const SIDEBAR_COLLAPSED = "var(--sidebar-collapsed-width)";
/** 与 --transition-base (180ms) 对齐，略加缓冲避免 transitionend 未触发时锁死 */
const TRANSITION_FALLBACK_MS = 220;

export function useSidebarShell() {
  const collapsed = useLocalStorageState<boolean>("agent-router-sidebar-collapsed", false);
  const isMobile = useMediaQuery("(max-width: 768px)");
  const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)");
  const transitioning = ref(false);

  let transitionTimer: ReturnType<typeof setTimeout> | null = null;

  const isCompact = computed(() => collapsed.value || isMobile.value);

  const currentWidth = computed(() =>
    isCompact.value ? SIDEBAR_COLLAPSED : SIDEBAR_EXPANDED
  );

  function finishTransition() {
    if (transitionTimer !== null) {
      clearTimeout(transitionTimer);
      transitionTimer = null;
    }
    transitioning.value = false;
  }

  function toggle() {
    if (transitioning.value) return;
    if (!prefersReducedMotion.value) {
      transitioning.value = true;
      transitionTimer = setTimeout(finishTransition, TRANSITION_FALLBACK_MS);
    }
    collapsed.value = !collapsed.value;
  }

  function onTransitionEnd(event: TransitionEvent) {
    if (event.target !== event.currentTarget || event.propertyName !== "width") return;
    finishTransition();
  }

  onScopeDispose(finishTransition);

  return {
    collapsed,
    isMobile,
    transitioning,
    isCompact,
    currentWidth,
    toggle,
    onTransitionEnd,
  };
}
