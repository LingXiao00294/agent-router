import { computed, ref } from "vue";
import { defineStore } from "pinia";
import { useLocalStorage } from "@vueuse/core";
import * as api from "@/api";
import type { AppConfig, CircuitBreakerMap, RouterMode } from "@/api/types";
import { useConfigStore } from "@/stores/config";

export type ThemeMode = "light" | "dark";

export const useAppStore = defineStore("app", () => {
  const theme = useLocalStorage<ThemeMode>("ar-theme", "light");
  const healthy = ref<boolean | null>(null);
  const healthError = ref<string | null>(null);
  const config = ref<AppConfig | null>(null);
  const configLoading = ref(false);
  const configError = ref<string | null>(null);
  const circuit = ref<CircuitBreakerMap>({});
  const savingMode = ref(false);
  const staleData = ref(false);

  const mode = computed(() => config.value?.router.mode ?? "failover");

  function applyTheme(next: ThemeMode) {
    theme.value = next;
    document.documentElement.setAttribute("data-theme", next);
  }

  function initTheme() {
    applyTheme(theme.value);
  }

  function toggleTheme() {
    applyTheme(theme.value === "light" ? "dark" : "light");
  }

  async function checkHealth() {
    try {
      const res = await api.getHealth();
      healthy.value = res.status === "ok";
      healthError.value = null;
    } catch (err) {
      healthy.value = false;
      healthError.value = err instanceof Error ? err.message : "unreachable";
    }
  }

  async function loadConfig(silent = false) {
    if (!silent) configLoading.value = true;
    configError.value = null;
    try {
      config.value = await api.getConfig();
    } catch (err) {
      configError.value = err instanceof Error ? err.message : "加载配置失败";
      if (!silent) throw err;
    } finally {
      configLoading.value = false;
    }
  }

  async function loadCircuit(silent = false) {
    try {
      circuit.value = await api.getCircuitBreaker();
    } catch (err) {
      if (!silent) throw err;
    }
  }

  /** Immediate mode PUT via config store sanitize path; syncs app.config after. */
  async function setMode(next: RouterMode) {
    if (savingMode.value) return;
    const configStore = useConfigStore();
    if (configStore.dirty) {
      throw new Error("配置页有未保存更改，请先保存或重载后再切换 Mode");
    }
    const prev = config.value?.router.mode;
    if (prev === next) return;
    savingMode.value = true;
    try {
      await configStore.setRouterMode(next);
      await loadConfig(true);
    } catch (err) {
      if (config.value && prev) {
        config.value = {
          ...config.value,
          router: { ...config.value.router, mode: prev },
        };
      }
      throw err;
    } finally {
      savingMode.value = false;
    }
  }

  const openCircuits = computed(() =>
    Object.entries(circuit.value).filter(([, s]) => s !== "closed"),
  );

  return {
    theme,
    healthy,
    healthError,
    config,
    configLoading,
    configError,
    circuit,
    savingMode,
    staleData,
    mode,
    openCircuits,
    applyTheme,
    initTheme,
    toggleTheme,
    checkHealth,
    loadConfig,
    loadCircuit,
    setMode,
  };
});
