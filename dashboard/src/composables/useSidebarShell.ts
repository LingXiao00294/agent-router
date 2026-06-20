import { computed, ref } from "vue";
import { useLocalStorageState } from "./useLocalStorageState";

const SIDEBAR_EXPANDED = "var(--sidebar-width)";
const SIDEBAR_COLLAPSED = "var(--sidebar-collapsed-width)";

export function useSidebarShell() {
  const collapsed = useLocalStorageState<boolean>("agent-router-sidebar-collapsed", false);
  const transitioning = ref(false);

  /** 紧凑布局仅跟随最终收起状态，具体变化由 CSS transition 平滑过渡 */
  const isCompact = computed(() => collapsed.value);

  const currentWidth = computed(() =>
    collapsed.value ? SIDEBAR_COLLAPSED : SIDEBAR_EXPANDED
  );

  function toggle() {
    if (transitioning.value) return;
    transitioning.value = true;
    collapsed.value = !collapsed.value;
  }

  function onTransitionEnd(event: TransitionEvent) {
    if (event.target !== event.currentTarget || event.propertyName !== "width") return;
    transitioning.value = false;
  }

  return {
    collapsed,
    transitioning,
    isCompact,
    currentWidth,
    toggle,
    onTransitionEnd,
  };
}
