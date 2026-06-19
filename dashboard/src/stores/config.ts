import { defineStore } from "pinia";
import { ref, computed } from "vue";
import {
  fetchConfig,
  fetchConfigModels,
  updateConfig,
  fetchCircuitBreakerStates,
  resetCircuitBreaker,
  type ServerConfig,
  type RouterConfig,
  type ProviderConfig,
  type ModelRef,
} from "../api";

export interface ProviderEntry {
  id: number;
  name: string;
  type: string;
  api_key: string;
  base_url: string;
  timeout_seconds: number;
  has_key: boolean;
  failure_threshold: number | null;
  recovery_timeout: number | null;
}

export interface ModelRefEntry extends ModelRef {
  id: number;
}

export interface ModelEntry {
  id: number;
  name: string;
  refs: ModelRefEntry[];
}

// 前端-only 的稳定 id，用作 v-for key，避免增删/重排时组件实例错位。
// 不会进入 buildConfigBody，不发给后端。
let _idSeed = 0;
const nextId = () => ++_idSeed;

const DEFAULT_SERVER: ServerConfig = {
  host: "127.0.0.1",
  port: 9456,
  log_level: "info",
  log_file: "logs/agent-router.log",
  log_max_bytes: 10_000_000,
  log_backup_count: 5,
};

const DEFAULT_ROUTER: RouterConfig = {
  failure_threshold: 5,
  recovery_timeout: 600,
};

export const useConfigStore = defineStore("config", () => {
  const serverConfig = ref<ServerConfig>({ ...DEFAULT_SERVER });
  const routerConfig = ref<RouterConfig>({ ...DEFAULT_ROUTER });
  const providerEntries = ref<ProviderEntry[]>([]);
  const modelEntries = ref<ModelEntry[]>([]);
  const circuitStates = ref<Record<string, string>>({});
  const circuitLoading = ref(false);
  const circuitError = ref<string | null>(null);
  const resetting = ref<string | null>(null);

  const loading = ref(false);
  const saving = ref(false);
  const error = ref<string | null>(null);
  const validationErrors = ref<Record<string, string>>({});

  const initialSnapshot = ref<string>("");

  const providerNames = computed(() =>
    providerEntries.value.map((p) => p.name).filter(Boolean)
  );

  const isDirty = computed(() => {
    const current = JSON.stringify({
      server: serverConfig.value,
      router: routerConfig.value,
      providers: providerEntries.value,
      models: modelEntries.value,
    });
    return current !== initialSnapshot.value;
  });

  function providerByName(name: string): ProviderEntry | undefined {
    return providerEntries.value.find((p) => p.name === name);
  }

  function snapshot() {
    initialSnapshot.value = JSON.stringify({
      server: serverConfig.value,
      router: routerConfig.value,
      providers: providerEntries.value,
      models: modelEntries.value,
    });
  }

  async function loadCircuitStates() {
    circuitLoading.value = true;
    circuitError.value = null;
    try {
      circuitStates.value = await fetchCircuitBreakerStates();
    } catch (err) {
      circuitStates.value = {};
      circuitError.value = err instanceof Error ? err.message : "加载熔断状态失败";
    } finally {
      circuitLoading.value = false;
    }
  }

  async function loadConfig() {
    loading.value = true;
    error.value = null;
    try {
      const [cfg, models] = await Promise.all([fetchConfig(), fetchConfigModels()]);

      serverConfig.value = {
        host: cfg.server?.host ?? DEFAULT_SERVER.host,
        port: cfg.server?.port ?? DEFAULT_SERVER.port,
        log_level: cfg.server?.log_level ?? DEFAULT_SERVER.log_level,
        log_file: cfg.server?.log_file ?? DEFAULT_SERVER.log_file,
        log_max_bytes: cfg.server?.log_max_bytes ?? DEFAULT_SERVER.log_max_bytes,
        log_backup_count: cfg.server?.log_backup_count ?? DEFAULT_SERVER.log_backup_count,
      };
      routerConfig.value = {
        failure_threshold: cfg.router?.failure_threshold ?? DEFAULT_ROUTER.failure_threshold,
        recovery_timeout: cfg.router?.recovery_timeout ?? DEFAULT_ROUTER.recovery_timeout,
      };

      providerEntries.value = Object.entries(cfg.providers || {}).map(([name, p]) => ({
        id: nextId(),
        name,
        type: p.type || "anthropic",
        api_key: p.api_key || "",
        base_url: p.base_url || "",
        timeout_seconds: p.timeout_seconds || 120,
        has_key: !!p.has_key,
        failure_threshold: p.failure_threshold ?? null,
        recovery_timeout: p.recovery_timeout ?? null,
      }));

      modelEntries.value = Object.entries(models || {}).map(([name, refs]) => ({
        id: nextId(),
        name,
        refs: (refs || []).map((r) => ({
          id: nextId(),
          provider: r.provider || "",
          model: r.model || "",
          priority: r.priority || 99,
        })),
      }));

      await loadCircuitStates();
      snapshot();
    } catch (err) {
      error.value = err instanceof Error ? err.message : "加载配置失败";
      throw err;
    } finally {
      loading.value = false;
    }
  }

  async function saveConfig(): Promise<boolean> {
    if (!validate()) return false;

    saving.value = true;
    error.value = null;
    try {
      const body = buildConfigBody();
      await updateConfig(body);
      await loadConfig();
      return true;
    } catch (err) {
      error.value = err instanceof Error ? err.message : "保存失败";
      throw err;
    } finally {
      saving.value = false;
    }
  }

  function buildConfigBody() {
    const providers: Record<string, ProviderConfig> = {};
    for (const p of providerEntries.value) {
      if (!p.name.trim()) continue;
      providers[p.name] = {
        type: p.type,
        api_key: p.api_key || "${PLACEHOLDER}",
        base_url: p.base_url,
        timeout_seconds: p.timeout_seconds,
        failure_threshold: p.failure_threshold ?? null,
        recovery_timeout: p.recovery_timeout ?? null,
      };
    }

    const models: Record<string, ModelRef[]> = {};
    for (const m of modelEntries.value) {
      if (!m.name.trim() || m.refs.length === 0) continue;
      models[m.name] = m.refs
        .filter((r) => r.provider && r.model)
        .map((r, i) => ({
          provider: r.provider,
          model: r.model,
          priority: i + 1,
        }));
    }

    return {
      server: { ...serverConfig.value },
      router: { ...routerConfig.value },
      providers,
      models,
    };
  }

  function validate(): boolean {
    const errors: Record<string, string> = {};

    if (!serverConfig.value.host.trim()) errors["server.host"] = "Host 不能为空";
    if (
      !Number.isInteger(serverConfig.value.port) ||
      serverConfig.value.port < 1 ||
      serverConfig.value.port > 65535
    ) {
      errors["server.port"] = "端口需在 1-65535 之间";
    }
    if (
      !Number.isInteger(routerConfig.value.failure_threshold) ||
      routerConfig.value.failure_threshold < 0
    ) {
      errors["router.failure_threshold"] = "需为大于等于 0 的整数";
    }
    if (
      !Number.isInteger(routerConfig.value.recovery_timeout) ||
      routerConfig.value.recovery_timeout <= 0
    ) {
      errors["router.recovery_timeout"] = "需为大于 0 的整数";
    }

    const names = new Set<string>();
    providerEntries.value.forEach((p, i) => {
      if (!p.name.trim()) errors[`providers[${i}].name`] = "Provider 名称不能为空";
      else if (names.has(p.name)) errors[`providers[${i}].name`] = "Provider 名称不能重复";
      else names.add(p.name);

      if (!p.type.trim()) errors[`providers[${i}].type`] = "类型不能为空";
      if (!p.base_url.trim()) errors[`providers[${i}].base_url`] = "Base URL 不能为空";
      if (!Number.isInteger(p.timeout_seconds) || p.timeout_seconds <= 0) {
        errors[`providers[${i}].timeout_seconds`] = "超时需为大于 0 的整数";
      }
    });

    const modelNames = new Set<string>();
    modelEntries.value.forEach((m, mi) => {
      if (!m.name.trim()) errors[`models[${mi}].name`] = "模型名称不能为空";
      else if (modelNames.has(m.name)) errors[`models[${mi}].name`] = "模型名称不能重复";
      else modelNames.add(m.name);

      if (m.refs.length === 0) {
        errors[`models[${mi}].refs`] = "至少需要一个 provider 映射";
      }
      m.refs.forEach((r, ri) => {
        if (!r.provider) errors[`models[${mi}].refs[${ri}].provider`] = "请选择 provider";
        if (!r.model.trim()) errors[`models[${mi}].refs[${ri}].model`] = "真实模型名不能为空";
      });
    });

    validationErrors.value = errors;
    return Object.keys(errors).length === 0;
  }

  function fieldError(path: string): string | undefined {
    return validationErrors.value[path];
  }

  async function handleResetCircuitBreaker(provider: string) {
    resetting.value = provider;
    try {
      await resetCircuitBreaker(provider);
      await loadCircuitStates();
    } finally {
      resetting.value = null;
    }
  }

  function addProvider() {
    providerEntries.value.push({
      id: nextId(),
      name: "",
      type: "anthropic",
      api_key: "",
      base_url: "",
      timeout_seconds: 120,
      has_key: false,
      failure_threshold: null,
      recovery_timeout: null,
    });
  }

  function removeProvider(idx: number) {
    const p = providerEntries.value[idx];
    if (!p) return;
    const name = p.name;
    providerEntries.value.splice(idx, 1);
    if (name) {
      for (const m of modelEntries.value) {
        m.refs = m.refs.filter((r) => r.provider !== name);
      }
    }
  }

  function addModel() {
    modelEntries.value.push({ id: nextId(), name: "", refs: [] });
  }

  function removeModel(idx: number) {
    modelEntries.value.splice(idx, 1);
  }

  function addRef(model: ModelEntry) {
    model.refs.push({
      id: nextId(),
      provider: "",
      model: "",
      priority: model.refs.length + 1,
    });
  }

  function removeRef(model: ModelEntry, idx: number) {
    model.refs.splice(idx, 1);
    recomputePriorities(model);
  }

  function moveRef(model: ModelEntry, from: number, to: number) {
    if (to < 0 || to >= model.refs.length) return;
    const [item] = model.refs.splice(from, 1);
    model.refs.splice(to, 0, item);
    recomputePriorities(model);
  }

  function recomputePriorities(model: ModelEntry) {
    model.refs.forEach((r, i) => {
      r.priority = i + 1;
    });
  }

  return {
    serverConfig,
    routerConfig,
    providerEntries,
    modelEntries,
    circuitStates,
    circuitLoading,
    circuitError,
    resetting,
    loading,
    saving,
    error,
    validationErrors,
    providerNames,
    isDirty,
    providerByName,
    loadConfig,
    saveConfig,
    buildConfigBody,
    validate,
    fieldError,
    loadCircuitStates,
    handleResetCircuitBreaker,
    addProvider,
    removeProvider,
    addModel,
    removeModel,
    addRef,
    removeRef,
    moveRef,
    recomputePriorities,
  };
});
