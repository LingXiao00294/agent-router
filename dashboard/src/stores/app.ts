import { defineStore } from "pinia";
import { ref, computed, watch } from "vue";
import { usePreferredDark } from "@vueuse/core";
import { useLocalStorageState } from "../composables/useLocalStorageState";
import { useSidebarShell } from "../composables/useSidebarShell";
import {
  CONFIG_NAV_ITEMS,
  DEFAULT_CONFIG_NAV_ORDER,
  resolveConfigNavOrder,
} from "../config/nav";

type ThemeMode = "dark" | "light" | "system";

export const useAppStore = defineStore("app", () => {
  const themeMode = ref<ThemeMode>("dark");
  const sidebar = useSidebarShell();
  const configNavOrder = useLocalStorageState<string[]>(
    "agent-router-config-nav-order",
    DEFAULT_CONFIG_NAV_ORDER,
    {
      deserialize: (raw) => resolveConfigNavOrder(JSON.parse(raw) as string[]),
    }
  );
  const preferredDark = usePreferredDark();

  const orderedConfigNavItems = computed(() => {
    const byId = new Map(CONFIG_NAV_ITEMS.map((item) => [item.id, item]));
    return resolveConfigNavOrder(configNavOrder.value)
      .map((id) => byId.get(id))
      .filter((item): item is (typeof CONFIG_NAV_ITEMS)[number] => !!item);
  });

  const resolvedTheme = computed<"dark" | "light">(() => {
    if (themeMode.value === "system") return preferredDark.value ? "dark" : "light";
    return themeMode.value;
  });

  function setTheme(mode: ThemeMode) {
    themeMode.value = mode;
    localStorage.setItem("agent-router-theme", mode);
    applyTheme();
  }

  function loadTheme() {
    const stored = localStorage.getItem("agent-router-theme") as ThemeMode | null;
    if (stored && ["dark", "light", "system"].includes(stored)) {
      themeMode.value = stored;
    }
    applyTheme();
  }

  function applyTheme() {
    document.documentElement.setAttribute("data-theme", resolvedTheme.value);
  }

  // system 模式下，OS 深/浅色变化时自动跟随（setTheme/loadTheme 已各自立即应用一次）
  watch(resolvedTheme, applyTheme);

  function toggleSidebar() {
    sidebar.toggle();
  }

  function reorderConfigNav(from: number, to: number) {
    if (from === to) return;
    const order = [...configNavOrder.value];
    const [item] = order.splice(from, 1);
    if (!item) return;
    order.splice(to, 0, item);
    configNavOrder.value = order;
  }

  return {
    themeMode,
    sidebarCollapsed: sidebar.collapsed,
    sidebarTransitioning: sidebar.transitioning,
    sidebarIsCompact: sidebar.isCompact,
    sidebarCurrentWidth: sidebar.currentWidth,
    onSidebarTransitionEnd: sidebar.onTransitionEnd,
    configNavOrder,
    orderedConfigNavItems,
    resolvedTheme,
    setTheme,
    loadTheme,
    toggleSidebar,
    reorderConfigNav,
  };
});
