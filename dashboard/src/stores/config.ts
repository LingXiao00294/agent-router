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
  type VirtualModelConfig,
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
  max_concurrent: number;
  max_queue: number;
  queue_wait_timeout: number;
  rate_limit_cooldown: number;
}

export interface ModelRefEntry extends ModelRef {
  id: number;
}

export interface ModelEntry {
  id: number;
  name: string;
  pinned_provider: string | null;
  pinned_model: string | null;
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
  mode: "failover",
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
  /** 至少成功加载过一次配置；未就绪时禁止模式开关，避免用空默认值覆盖服务端 */
  const configReady = ref(false);
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
        mode: cfg.router?.mode === "sticky" ? "sticky" : "failover",
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
        max_concurrent: p.max_concurrent ?? 0,
        max_queue: p.max_queue ?? 0,
        queue_wait_timeout: p.queue_wait_timeout ?? 30,
        rate_limit_cooldown: p.rate_limit_cooldown ?? 30,
      }));

      modelEntries.value = Object.entries(models || {}).map(([name, entry]) => {
        const vm = normalizeVirtualModel(entry);
        return {
          id: nextId(),
          name,
          pinned_provider: vm.pinned_provider ?? null,
          pinned_model: vm.pinned_model ?? null,
          refs: vm.providers.map((r) => ({
            id: nextId(),
            provider: r.provider || "",
            model: r.model || "",
            priority: r.priority || 99,
          })),
        };
      });

      await loadCircuitStates();
      snapshot();
      configReady.value = true;
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

  function normalizeVirtualModel(
    entry: VirtualModelConfig | ModelRef[] | undefined
  ): VirtualModelConfig {
    if (Array.isArray(entry)) {
      return { providers: entry };
    }
    if (entry && typeof entry === "object" && Array.isArray(entry.providers)) {
      return {
        pinned_provider: entry.pinned_provider ?? null,
        pinned_model: entry.pinned_model ?? null,
        providers: entry.providers,
      };
    }
    return { providers: [] };
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
        max_concurrent: p.max_concurrent || 0,
        max_queue: p.max_queue || 0,
        queue_wait_timeout: p.queue_wait_timeout || 30,
        rate_limit_cooldown: p.rate_limit_cooldown || 30,
      };
    }

    const models: Record<string, VirtualModelConfig> = {};
    for (const m of modelEntries.value) {
      if (!m.name.trim() || m.refs.length === 0) continue;
      const providersList = m.refs
        .filter((r) => r.provider && r.model)
        .map((r, i) => ({
          provider: r.provider,
          model: r.model,
          priority: i + 1,
        }));
      // failover 不提交过期 pin，避免改 ref 后 pin 不匹配导致后端校验失败
      const modelCfg: VirtualModelConfig = { providers: providersList };
      if (routerConfig.value.mode === "sticky") {
        modelCfg.pinned_provider = m.pinned_provider;
        modelCfg.pinned_model = m.pinned_model;
      }
      models[m.name] = modelCfg;
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
      if (!Number.isInteger(p.max_concurrent) || p.max_concurrent < 0) {
        errors[`providers[${i}].max_concurrent`] = "需为大于等于 0 的整数";
      }
      if (!Number.isInteger(p.max_queue) || p.max_queue < 0) {
        errors[`providers[${i}].max_queue`] = "需为大于等于 0 的整数";
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
      if (routerConfig.value.mode === "sticky") {
        const pinnedOk = m.refs.some(
          (r) => r.provider === m.pinned_provider && r.model === m.pinned_model
        );
        if (!m.pinned_provider || !m.pinned_model || !pinnedOk) {
          errors[`models[${mi}].pinned`] = "指定模型模式下请选择链中的一项";
        }
      }
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
      max_concurrent: 0,
      max_queue: 0,
      queue_wait_timeout: 30,
      rate_limit_cooldown: 30,
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
        if (m.pinned_provider === name) {
          m.pinned_provider = null;
          m.pinned_model = null;
        }
      }
    }
  }

  function addModel() {
    modelEntries.value.push({
      id: nextId(),
      name: "",
      pinned_provider: null,
      pinned_model: null,
      refs: [],
    });
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
    const removed = model.refs[idx];
    model.refs.splice(idx, 1);
    recomputePriorities(model);
    if (
      removed &&
      model.pinned_provider === removed.provider &&
      model.pinned_model === removed.model
    ) {
      model.pinned_provider = null;
      model.pinned_model = null;
    }
  }

  function pinRef(model: ModelEntry, idx: number) {
    const ref = model.refs[idx];
    if (!ref) return;
    model.pinned_provider = ref.provider;
    model.pinned_model = ref.model;
  }

  async function setRouterMode(mode: "failover" | "sticky"): Promise<boolean> {
    if (!configReady.value || loading.value) {
      error.value = "配置尚未加载完成，请稍后再试";
      return false;
    }

    const previousMode = routerConfig.value.mode;
    const previousPins = modelEntries.value.map((m) => ({
      id: m.id,
      pinned_provider: m.pinned_provider,
      pinned_model: m.pinned_model,
    }));

    routerConfig.value.mode = mode;
    if (mode === "sticky") {
      for (const m of modelEntries.value) {
        if (!m.pinned_provider && m.refs.length > 0) {
          const first = m.refs[0];
          m.pinned_provider = first.provider || null;
          m.pinned_model = first.model || null;
        }
      }
    }

    try {
      const ok = await saveConfig();
      if (!ok) {
        routerConfig.value.mode = previousMode;
        for (const prev of previousPins) {
          const m = modelEntries.value.find((entry) => entry.id === prev.id);
          if (m) {
            m.pinned_provider = prev.pinned_provider;
            m.pinned_model = prev.pinned_model;
          }
        }
      }
      return ok;
    } catch (err) {
      routerConfig.value.mode = previousMode;
      for (const prev of previousPins) {
        const m = modelEntries.value.find((entry) => entry.id === prev.id);
        if (m) {
          m.pinned_provider = prev.pinned_provider;
          m.pinned_model = prev.pinned_model;
        }
      }
      throw err;
    }
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
    configReady,
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
    pinRef,
    setRouterMode,
    moveRef,
    recomputePriorities,
  };
});
