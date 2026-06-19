import { defineStore } from "pinia";
import { ref, computed, watch } from "vue";
import { usePreferredDark } from "@vueuse/core";
import { useLocalStorageState } from "../composables/useLocalStorageState";

type ThemeMode = "dark" | "light" | "system";

export const useAppStore = defineStore("app", () => {
  const themeMode = ref<ThemeMode>("dark");
  const sidebarCollapsed = useLocalStorageState<boolean>(
    "agent-router-sidebar-collapsed",
    false
  );
  const preferredDark = usePreferredDark();

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
    sidebarCollapsed.value = !sidebarCollapsed.value;
  }

  return {
    themeMode,
    sidebarCollapsed,
    resolvedTheme,
    setTheme,
    loadTheme,
    toggleSidebar,
  };
});
