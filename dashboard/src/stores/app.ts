import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { usePreferredDark } from "@vueuse/core";

type ThemeMode = "dark" | "light" | "system";

export const useAppStore = defineStore("app", () => {
  const themeMode = ref<ThemeMode>("dark");
  const sidebarCollapsed = ref(false);
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
