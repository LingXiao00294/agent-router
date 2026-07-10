import { computed, ref } from "vue";
import { defineStore } from "pinia";
import * as api from "@/api";
import type {
  AppConfig,
  RouterMode,
  VirtualModelConfig,
} from "@/api/types";
import {
  buildPutPayload,
  captureMaskedApiKeys,
  emptyRouter,
  emptyServer,
  isBackendMaskedShape,
  isBlankOrPlaceholderKey,
  normalizeAppConfig,
  normalizeModels,
} from "@/utils/configPayload";

function cloneConfig(c: AppConfig): AppConfig {
  return structuredClone(c);
}

export const useConfigStore = defineStore("config", () => {
  const draft = ref<AppConfig | null>(null);
  const baseline = ref<string>("");
  const knownProviders = ref<Set<string>>(new Set());
  const maskedApiKeys = ref<Record<string, string>>({});
  const models = ref<Record<string, VirtualModelConfig>>({});
  const loading = ref(false);
  const saving = ref(false);
  const error = ref<string | null>(null);
  const fieldErrors = ref<Record<string, string>>({});
  let loadPromise: Promise<void> | null = null;

  const dirty = computed(() => {
    if (!draft.value) return false;
    return JSON.stringify(buildPayload()) !== baseline.value;
  });

  function buildPayload(): AppConfig {
    if (!draft.value) {
      return {
        server: emptyServer(),
        router: emptyRouter(),
        providers: {},
        models: {},
      };
    }
    return buildPutPayload(draft.value, models.value, maskedApiKeys.value);
  }

  /** Reuse the active request so callers always initialize one consistent draft. */
  function load(): Promise<void> {
    if (loadPromise) return loadPromise;

    const request = (async () => {
      loading.value = true;
      error.value = null;
      try {
        const [cfg, normModels] = await Promise.all([
          api.getConfig(),
          api.getConfigModels(),
        ]);
        const normalized = normalizeAppConfig(cfg);
        draft.value = cloneConfig(normalized);
        models.value = normalizeModels(normalized.models, normModels);
        knownProviders.value = new Set(Object.keys(normalized.providers));
        maskedApiKeys.value = captureMaskedApiKeys(normalized.providers);
        baseline.value = JSON.stringify(buildPayload());
        fieldErrors.value = {};
      } catch (err) {
        error.value = err instanceof Error ? err.message : "加载配置失败";
        throw err;
      } finally {
        loading.value = false;
      }
    })();
    loadPromise = request;
    void request.then(
      () => {
        if (loadPromise === request) loadPromise = null;
      },
      () => {
        if (loadPromise === request) loadPromise = null;
      },
    );
    return request;
  }

  function validate(): boolean {
    const errs: Record<string, string> = {};
    if (!draft.value) {
      fieldErrors.value = { _: "配置未加载" };
      return false;
    }
    const s = draft.value.server;
    if (!s.host.trim()) errs["server.host"] = "host 不能为空";
    if (!Number.isFinite(s.port) || s.port < 1 || s.port > 65535) {
      errs["server.port"] = "端口需在 1–65535";
    }
    if (!Number.isFinite(s.log_max_bytes) || s.log_max_bytes < 0) {
      errs["server.log_max_bytes"] = "需为 ≥ 0 的数字";
    }
    if (!Number.isFinite(s.log_backup_count) || s.log_backup_count < 0) {
      errs["server.log_backup_count"] = "需为 ≥ 0 的数字";
    }
    if (
      !Number.isFinite(draft.value.router.failure_threshold) ||
      draft.value.router.failure_threshold < 0
    ) {
      errs["router.failure_threshold"] = "需 ≥ 0";
    }
    if (
      !Number.isFinite(draft.value.router.recovery_timeout) ||
      draft.value.router.recovery_timeout <= 0
    ) {
      errs["router.recovery_timeout"] = "需 > 0";
    }

    if (!Object.keys(draft.value.providers).length) {
      errs.providers = "至少保留一个 provider";
    }
    if (!Object.keys(models.value).length) {
      errs.models = "至少保留一个虚拟模型";
    }

    for (const [name, p] of Object.entries(draft.value.providers)) {
      if (!p.base_url.trim()) errs[`providers.${name}.base_url`] = "必填";
      if (!Number.isFinite(p.timeout_seconds) || p.timeout_seconds <= 0) {
        errs[`providers.${name}.timeout`] = "需 > 0";
      }
      if (
        p.max_concurrent != null &&
        (!Number.isFinite(p.max_concurrent) || p.max_concurrent < 0)
      ) {
        errs[`providers.${name}.max_concurrent`] = "需 ≥ 0";
      }
      if (
        p.max_queue != null &&
        (!Number.isFinite(p.max_queue) || p.max_queue < 0)
      ) {
        errs[`providers.${name}.max_queue`] = "需 ≥ 0";
      }
      if (
        p.queue_wait_timeout != null &&
        (!Number.isFinite(p.queue_wait_timeout) || p.queue_wait_timeout <= 0)
      ) {
        errs[`providers.${name}.queue_wait_timeout`] = "需 > 0";
      }
      if (
        p.rate_limit_cooldown != null &&
        (!Number.isFinite(p.rate_limit_cooldown) || p.rate_limit_cooldown <= 0)
      ) {
        errs[`providers.${name}.rate_limit_cooldown`] = "需 > 0";
      }
      if (
        p.failure_threshold != null &&
        (!Number.isFinite(p.failure_threshold) || p.failure_threshold < 0)
      ) {
        errs[`providers.${name}.failure_threshold`] = "需 ≥ 0 或留空";
      }
      if (
        p.recovery_timeout != null &&
        (!Number.isFinite(p.recovery_timeout) || p.recovery_timeout <= 0)
      ) {
        errs[`providers.${name}.recovery_timeout`] = "需 > 0 或留空";
      }
      if (!knownProviders.value.has(name)) {
        if (isBackendMaskedShape(p.api_key)) {
          errs[`providers.${name}.api_key`] = "新建 provider 需要有效 api_key";
        }
      } else if (
        isBackendMaskedShape(p.api_key) &&
        !isBlankOrPlaceholderKey(p.api_key) &&
        p.api_key !== maskedApiKeys.value[name]
      ) {
        errs[`providers.${name}.api_key`] =
          "不能使用脱敏形态的密钥；请输入完整 api_key 或留空保留";
      }
    }

    for (const [name, m] of Object.entries(models.value)) {
      if (!m.providers.length) {
        errs[`models.${name}`] = "至少一条 provider 引用";
      }
      m.providers.forEach((r, i) => {
        if (!r.provider?.trim() || !(r.provider in draft.value!.providers)) {
          errs[`models.${name}.ref.${i}`] = "provider 无效或不存在";
        }
        if (!r.model?.trim()) {
          errs[`models.${name}.ref.${i}.model`] = "model 不能为空";
        }
      });
      if (draft.value.router.mode === "sticky") {
        const ok =
          m.pinned_provider &&
          m.pinned_model &&
          m.providers.some(
            (r) =>
              r.provider === m.pinned_provider && r.model === m.pinned_model,
          );
        if (!ok) {
          errs[`models.${name}.pin`] = "sticky 模式需要有效 pin";
        }
      }
    }

    fieldErrors.value = errs;
    return Object.keys(errs).length === 0;
  }

  async function save() {
    if (!draft.value) return;
    if (!validate()) {
      throw new Error("请先修正表单错误");
    }
    saving.value = true;
    error.value = null;
    try {
      const payload = buildPayload();
      await api.putConfig(payload);
      await load();
    } catch (err) {
      error.value = err instanceof Error ? err.message : "保存失败";
      throw err;
    } finally {
      saving.value = false;
    }
  }

  /** Top-bar immediate mode switch: refuses when config page has unsaved edits. */
  async function setRouterMode(next: RouterMode) {
    if (dirty.value) {
      throw new Error("配置页有未保存更改，请先保存或重载后再切换 Mode");
    }
    if (!draft.value) {
      await load();
    }
    if (!draft.value) {
      throw new Error("配置未加载");
    }
    if (draft.value.router.mode === next) return;

    saving.value = true;
    error.value = null;
    const prev = draft.value.router.mode;
    draft.value = {
      ...draft.value,
      router: { ...draft.value.router, mode: next },
    };
    try {
      if (!validate()) {
        draft.value = {
          ...draft.value,
          router: { ...draft.value.router, mode: prev },
        };
        const firstError =
          Object.entries(fieldErrors.value).find(([key]) => key.endsWith(".pin")) ??
          Object.entries(fieldErrors.value)[0];
        throw new Error(
          firstError
            ? `无法切换 Mode：请先修正「${firstError[0]}」：${firstError[1]}`
            : "配置校验失败，无法切换 Mode",
        );
      }
      await api.putConfig(buildPayload());
      await load();
    } catch (err) {
      if (draft.value && draft.value.router.mode === next) {
        draft.value = {
          ...draft.value,
          router: { ...draft.value.router, mode: prev },
        };
      }
      error.value = err instanceof Error ? err.message : "切换 Mode 失败";
      throw err;
    } finally {
      saving.value = false;
    }
  }

  function addProvider(name: string) {
    if (!draft.value || !name.trim()) return;
    if (draft.value.providers[name]) {
      fieldErrors.value = { ...fieldErrors.value, providers: "名称已存在" };
      return;
    }
    const { providers: _nameError, ...remainingErrors } = fieldErrors.value;
    void _nameError;
    fieldErrors.value = remainingErrors;
    draft.value.providers[name] = {
      type: "anthropic",
      api_key: "",
      base_url: "",
      timeout_seconds: 120,
      failure_threshold: null,
      recovery_timeout: null,
      max_concurrent: 0,
      max_queue: 0,
      queue_wait_timeout: 30,
      rate_limit_cooldown: 30,
      has_key: false,
    };
  }

  function removeProvider(name: string) {
    if (!draft.value) return;
    delete draft.value.providers[name];
    knownProviders.value.delete(name);
    const { [name]: _removed, ...rest } = maskedApiKeys.value;
    void _removed;
    maskedApiKeys.value = rest;
    for (const m of Object.values(models.value)) {
      m.providers = m.providers.filter((r) => r.provider !== name);
      if (m.pinned_provider === name) {
        m.pinned_provider = null;
        m.pinned_model = null;
      }
    }
  }

  function addModel(name: string) {
    if (!name.trim() || models.value[name]) return;
    models.value[name] = {
      pinned_provider: null,
      pinned_model: null,
      providers: [],
    };
  }

  function removeModel(name: string) {
    delete models.value[name];
  }

  function renameModel(oldName: string, newName: string) {
    if (!newName.trim() || oldName === newName || models.value[newName]) return;
    models.value[newName] = models.value[oldName];
    delete models.value[oldName];
  }

  function moveRef(model: string, from: number, to: number) {
    const m = models.value[model];
    if (!m) return;
    const list = [...m.providers];
    if (from < 0 || from >= list.length || to < 0 || to >= list.length) return;
    const [item] = list.splice(from, 1);
    list.splice(to, 0, item);
    m.providers = list;
  }

  return {
    draft,
    models,
    loading,
    saving,
    error,
    fieldErrors,
    dirty,
    load,
    save,
    setRouterMode,
    validate,
    buildPayload,
    addProvider,
    removeProvider,
    addModel,
    removeModel,
    renameModel,
    moveRef,
  };
});
