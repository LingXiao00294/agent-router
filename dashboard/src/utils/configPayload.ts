import type {
  AppConfig,
  LogLevel,
  ModelRef,
  ProviderConfig,
  ProviderType,
  RouterConfig,
  ServerConfig,
  VirtualModelConfig,
} from "@/api/types";

export function emptyServer(): ServerConfig {
  return {
    host: "127.0.0.1",
    port: 9456,
    log_level: "info",
    log_file: "logs/agent-router.log",
    log_max_bytes: 10_000_000,
    log_backup_count: 5,
  };
}

export function emptyRouter(): RouterConfig {
  return {
    failure_threshold: 5,
    recovery_timeout: 600,
    mode: "sticky",
  };
}

function asFinite(value: unknown, fallback: number): number {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function asNullableFinite(value: unknown): number | null {
  if (value == null || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

function optionalNonZeroPrice(value: number | undefined): number | undefined {
  return value != null && Number.isFinite(value) && value > 0 ? value : undefined;
}

const LOG_LEVELS: LogLevel[] = ["debug", "info", "warning", "error"];

/** Fill omitted provider fields with ProviderDef defaults. */
export function normalizeProviderConfig(
  raw: Partial<ProviderConfig> | Record<string, unknown> | null | undefined,
): ProviderConfig {
  const r = (raw ?? {}) as Record<string, unknown>;
  const type: ProviderType = r.type === "openai" ? "openai" : "anthropic";
  return {
    type,
    api_key: typeof r.api_key === "string" ? r.api_key : "",
    base_url: typeof r.base_url === "string" ? r.base_url : "",
    timeout_seconds: asFinite(r.timeout_seconds, 120),
    failure_threshold: asNullableFinite(r.failure_threshold),
    recovery_timeout: asNullableFinite(r.recovery_timeout),
    max_concurrent: asFinite(r.max_concurrent, 0),
    max_queue: asFinite(r.max_queue, 0),
    queue_wait_timeout: asFinite(r.queue_wait_timeout, 30),
    rate_limit_cooldown: asFinite(r.rate_limit_cooldown, 30),
    has_key: Boolean(r.has_key),
    api_key_unresolved: Boolean(r.api_key_unresolved),
  };
}

/**
 * Normalize GET /api/config raw TOML into a complete AppConfig.
 * Backend may omit [router]/[providers] and many default fields.
 */
export function normalizeAppConfig(
  raw: Partial<AppConfig> | Record<string, unknown> | null | undefined,
): AppConfig {
  const src = (raw ?? {}) as Partial<AppConfig> & Record<string, unknown>;
  const serverIn = (src.server ?? {}) as Partial<ServerConfig>;
  const routerIn = (src.router ?? {}) as Partial<RouterConfig>;
  const providersIn =
    src.providers && typeof src.providers === "object"
      ? (src.providers as Record<string, Partial<ProviderConfig>>)
      : {};

  const logLevel = serverIn.log_level;
  const server: ServerConfig = {
    host:
      typeof serverIn.host === "string" && serverIn.host
        ? serverIn.host
        : "127.0.0.1",
    port: asFinite(serverIn.port, 9456),
    log_level: LOG_LEVELS.includes(logLevel as LogLevel)
      ? (logLevel as LogLevel)
      : "info",
    log_file:
      typeof serverIn.log_file === "string"
        ? serverIn.log_file
        : "logs/agent-router.log",
    log_max_bytes: asFinite(serverIn.log_max_bytes, 10_000_000),
    log_backup_count: asFinite(serverIn.log_backup_count, 5),
  };

  const router: RouterConfig = {
    failure_threshold: asFinite(routerIn.failure_threshold, 5),
    recovery_timeout: asFinite(routerIn.recovery_timeout, 600),
    mode: routerIn.mode === "failover" ? "failover" : "sticky",
  };

  const providers: Record<string, ProviderConfig> = {};
  for (const [name, pdata] of Object.entries(providersIn)) {
    providers[name] = normalizeProviderConfig(pdata);
  }

  return {
    server,
    router,
    providers,
    models: (src.models as AppConfig["models"]) ?? {},
  };
}

/** Empty / placeholder / all-stars — always preserve server-side key. */
export function isBlankOrPlaceholderKey(key: string): boolean {
  return !key || key === "${PLACEHOLDER}" || /^\*+$/.test(key);
}

/**
 * Matches backend `_is_key_masked` shape (empty, placeholder, all-stars,
 * or prefix4 + stars + suffix4). Such values are never accepted as a new secret.
 */
export function isBackendMaskedShape(key: string): boolean {
  if (isBlankOrPlaceholderKey(key)) return true;
  if (key.length > 8) {
    const mid = key.slice(4, -4);
    if (mid.length > 0 && [...mid].every((c) => c === "*")) return true;
  }
  return false;
}

/**
 * Preserve existing api_key when blank/placeholder, equal to the GET masked
 * value, or otherwise matching backend masked shape (never treat as a new key).
 */
export function shouldPreserveApiKey(
  name: string,
  apiKey: string,
  originalMasked: Record<string, string>,
): boolean {
  if (isBlankOrPlaceholderKey(apiKey)) return true;
  if (
    Object.prototype.hasOwnProperty.call(originalMasked, name) &&
    apiKey === originalMasked[name]
  ) {
    return true;
  }
  return isBackendMaskedShape(apiKey);
}

export function captureMaskedApiKeys(
  providers: Record<string, ProviderConfig>,
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [name, p] of Object.entries(providers)) {
    out[name] = p.api_key ?? "";
  }
  return out;
}

export function normalizeModels(
  models: Record<string, VirtualModelConfig | ModelRef[]> | null | undefined,
  normalized?: Record<string, VirtualModelConfig>,
): Record<string, VirtualModelConfig> {
  const source = normalized ?? models ?? {};
  const out: Record<string, VirtualModelConfig> = {};
  for (const [name, entry] of Object.entries(source)) {
    let providers: ModelRef[];
    let pinnedProvider: string | null;
    let pinnedModel: string | null;
    if (Array.isArray(entry)) {
      providers = entry
        .map((r, i) => ({
          ...structuredClone(r),
          priority: r.priority ?? i + 1,
        }))
        .sort((a, b) => a.priority - b.priority);
      pinnedProvider = null;
      pinnedModel = null;
    } else {
      providers = structuredClone(entry.providers ?? []).sort(
        (a, b) => a.priority - b.priority,
      );
      pinnedProvider = entry.pinned_provider ?? null;
      pinnedModel = entry.pinned_model ?? null;
    }
    const pinValid = providers.some(
      (r) => r.provider === pinnedProvider && r.model === pinnedModel,
    );
    const defaultPin = providers.find((r) => r.provider.trim() && r.model.trim());
    out[name] = {
      pinned_provider: pinValid ? pinnedProvider : (defaultPin?.provider ?? null),
      pinned_model: pinValid ? pinnedModel : (defaultPin?.model ?? null),
      providers,
    };
  }
  return out;
}

export function buildPutPayload(
  draft: AppConfig,
  models: Record<string, VirtualModelConfig>,
  originalMasked: Record<string, string>,
): AppConfig {
  const providers: Record<string, ProviderConfig> = {};
  for (const [name, p] of Object.entries(draft.providers)) {
    const { has_key: _h, api_key_unresolved: _u, ...rest } = p;
    void _h;
    void _u;
    providers[name] = {
      ...rest,
      api_key: shouldPreserveApiKey(name, p.api_key, originalMasked)
        ? ""
        : p.api_key,
    };
  }

  const modelOut: Record<string, VirtualModelConfig> = {};
  for (const [name, m] of Object.entries(models)) {
    const providersList = m.providers.map((r, i) => ({
      provider: r.provider,
      model: r.model,
      priority: i + 1,
      input_price_per_million: optionalNonZeroPrice(r.input_price_per_million),
      output_price_per_million: optionalNonZeroPrice(r.output_price_per_million),
      cache_read_price_per_million: optionalNonZeroPrice(r.cache_read_price_per_million),
      cache_write_price_per_million: optionalNonZeroPrice(r.cache_write_price_per_million),
    }));
    if (providersList.length === 0) continue;
    let pinned_provider = m.pinned_provider ?? null;
    let pinned_model = m.pinned_model ?? null;
    const pinOk =
      pinned_provider &&
      pinned_model &&
      providersList.some(
        (r) => r.provider === pinned_provider && r.model === pinned_model,
      );
    if (!pinOk) {
      const defaultPin = providersList.find(
        (r) => r.provider.trim() && r.model.trim(),
      );
      pinned_provider = defaultPin?.provider ?? null;
      pinned_model = defaultPin?.model ?? null;
    }
    modelOut[name] = {
      pinned_provider,
      pinned_model,
      providers: providersList,
    };
  }

  return {
    server: { ...draft.server },
    router: { ...draft.router },
    providers,
    models: modelOut,
  };
}
