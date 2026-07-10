import type {
  AppConfig,
  ModelRef,
  ProviderConfig,
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
    mode: "failover",
  };
}

/** Empty / placeholder / all-stars — always preserve server-side key. */
export function isBlankOrPlaceholderKey(key: string): boolean {
  return !key || key === "${PLACEHOLDER}" || /^\*+$/.test(key);
}

/**
 * Preserve existing api_key only when blank/placeholder, or when the value
 * still equals the masked string returned by GET for that provider.
 * A newly typed key that merely *looks* masked is treated as a real key.
 */
export function shouldPreserveApiKey(
  name: string,
  apiKey: string,
  originalMasked: Record<string, string>,
): boolean {
  if (isBlankOrPlaceholderKey(apiKey)) return true;
  return (
    Object.prototype.hasOwnProperty.call(originalMasked, name) &&
    apiKey === originalMasked[name]
  );
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
  models: Record<string, VirtualModelConfig | ModelRef[]>,
  normalized?: Record<string, VirtualModelConfig>,
): Record<string, VirtualModelConfig> {
  if (normalized) return structuredClone(normalized);
  const out: Record<string, VirtualModelConfig> = {};
  for (const [name, entry] of Object.entries(models)) {
    if (Array.isArray(entry)) {
      out[name] = {
        pinned_provider: null,
        pinned_model: null,
        providers: entry.map((r, i) => ({
          ...r,
          priority: r.priority ?? i + 1,
        })),
      };
    } else {
      out[name] = {
        pinned_provider: entry.pinned_provider ?? null,
        pinned_model: entry.pinned_model ?? null,
        providers: [...(entry.providers ?? [])].sort(
          (a, b) => a.priority - b.priority,
        ),
      };
    }
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
      pinned_provider = null;
      pinned_model = null;
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
