import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { createPinia, setActivePinia } from "pinia";
import type { AppConfig, CallsPage, Summary } from "../src/api/types";
import { useCallsStore } from "../src/stores/calls";
import { useAppStore } from "../src/stores/app";
import { useConfigStore } from "../src/stores/config";
import { useMetricsStore } from "../src/stores/metrics";

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason?: unknown) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function callsPage(page: number): CallsPage {
  return {
    data: [],
    total: 3,
    page,
    size: 1,
    pages: 3,
  };
}

function summary(totalCalls: number): Summary {
  return {
    total_calls: totalCalls,
    success_count: totalCalls,
    error_count: 0,
    success_rate: 100,
    total_input_tokens: totalCalls,
    total_output_tokens: totalCalls,
    total_cache_read: 0,
    total_cache_write: 0,
    total_cost_usd: totalCalls,
    avg_latency_ms: totalCalls,
  };
}

function metricBatch(marker: number, fail = false): Response[] {
  return [
    fail
      ? jsonResponse({ detail: `metrics-${marker}-failed` }, 500)
      : jsonResponse(summary(marker)),
    jsonResponse([
      {
        provider: "provider",
        model: `real-${marker}`,
        count: marker,
        success_count: marker,
        total_input_tokens: marker,
        total_output_tokens: marker,
        total_cost_usd: marker,
      },
    ]),
    jsonResponse([
      {
        virtual_model: `virtual-${marker}`,
        count: marker,
        success_count: marker,
        total_input_tokens: marker,
        total_output_tokens: marker,
        total_cost_usd: marker,
      },
    ]),
    jsonResponse([{ provider: "provider", count: marker, success_count: marker }]),
    jsonResponse([]),
  ];
}

function validConfig(host = "127.0.0.1"): AppConfig {
  return {
    server: {
      host,
      port: 9456,
      log_level: "info",
      log_file: "",
      log_max_bytes: 10_485_760,
      log_backup_count: 0,
    },
    router: {
      failure_threshold: 5,
      recovery_timeout: 600,
      mode: "failover",
    },
    providers: {
      provider: {
        type: "anthropic",
        api_key: "test-key",
        base_url: "https://example.test/anthropic",
        timeout_seconds: 120,
        failure_threshold: null,
        recovery_timeout: null,
        max_concurrent: 0,
        max_queue: 0,
        queue_wait_timeout: 30,
        rate_limit_cooldown: 30,
        models: { real: {} },
      },
    },
    models: virtualModels(),
  };
}

function virtualModels(): AppConfig["models"] {
  return {
    virtual: {
      pinned_model: null,
      models: [{ provider: "provider", model: "real" }],
    },
  };
}

const originalFetch = globalThis.fetch;

beforeEach(() => setActivePinia(createPinia()));
afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("request generations", () => {
  test("app stores keep the newest global health, config, and circuit results", async () => {
    const health = [deferred<Response>(), deferred<Response>()];
    const configs = [deferred<Response>(), deferred<Response>()];
    const circuits = [deferred<Response>(), deferred<Response>()];
    const indexes = { health: 0, config: 0, circuit: 0 };
    globalThis.fetch = ((input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/health") return health[indexes.health++].promise;
      if (path === "/api/config") return configs[indexes.config++].promise;
      if (path === "/api/circuit-breaker") return circuits[indexes.circuit++].promise;
      throw new Error(`Unexpected request: ${path}`);
    }) as typeof fetch;
    const store = useAppStore();

    const first = [store.checkHealth(), store.loadConfig(), store.loadCircuit()];
    const second = [store.checkHealth(), store.loadConfig(), store.loadCircuit()];
    health[1].resolve(jsonResponse({ status: "ok" }));
    configs[1].resolve(jsonResponse(validConfig("newest")));
    circuits[1].resolve(jsonResponse({ provider: "open" }));
    await Promise.all(second);

    health[0].resolve(jsonResponse({ status: "down" }));
    configs[0].resolve(jsonResponse(validConfig("stale")));
    circuits[0].resolve(jsonResponse({ provider: "closed" }));
    await Promise.all(first);

    expect(store.healthy).toBe(true);
    expect(store.config?.server.host).toBe("newest");
    expect(store.circuit).toEqual({ provider: "open" });
    expect(store.configLoading).toBe(false);
  });

  test("calls keeps the newest page when responses and errors finish in reverse order", async () => {
    const requests = [deferred<Response>(), deferred<Response>(), deferred<Response>()];
    let requestIndex = 0;
    globalThis.fetch = (() => requests[requestIndex++].promise) as typeof fetch;
    const store = useCallsStore();

    const first = store.fetchList({ page: 1, size: 1 });
    const second = store.fetchList({ page: 2, size: 1 });
    const third = store.fetchList({ page: 3, size: 1 });

    requests[2].resolve(jsonResponse(callsPage(3)));
    await third;
    expect(store.page?.page).toBe(3);
    expect(store.loading).toBe(false);

    requests[1].resolve(jsonResponse({ detail: "old request failed" }, 500));
    await second;
    requests[0].resolve(jsonResponse(callsPage(1)));
    await first;

    expect(store.page?.page).toBe(3);
    expect(store.error).toBeNull();
    expect(store.loading).toBe(false);
  });

  test("calls keeps loading while the newest request is still pending", async () => {
    const requests = [deferred<Response>(), deferred<Response>()];
    let requestIndex = 0;
    globalThis.fetch = (() => requests[requestIndex++].promise) as typeof fetch;
    const store = useCallsStore();

    const oldRequest = store.fetchList({ page: 1, size: 1 });
    const newestRequest = store.fetchList({ page: 2, size: 1 });
    requests[0].resolve(jsonResponse(callsPage(1)));
    await oldRequest;
    expect(store.loading).toBe(true);

    requests[1].resolve(jsonResponse(callsPage(2)));
    await newestRequest;
    expect(store.loading).toBe(false);
  });

  test("metrics keeps the newest range when three batches finish newest-first", async () => {
    const requests = Array.from({ length: 15 }, () => deferred<Response>());
    let requestIndex = 0;
    globalThis.fetch = (() => requests[requestIndex++].promise) as typeof fetch;
    const store = useMetricsStore();

    const sevenDays = store.setDays(7);
    const thirtyDays = store.setDays(30);
    const ninetyDays = store.setDays(90);

    metricBatch(90).forEach((response, index) => requests[10 + index].resolve(response));
    await ninetyDays;
    metricBatch(30, true).forEach((response, index) => requests[5 + index].resolve(response));
    await thirtyDays;
    metricBatch(7).forEach((response, index) => requests[index].resolve(response));
    await sevenDays;

    expect(store.days).toBe(90);
    expect(store.summary?.total_calls).toBe(90);
    expect(store.byRealModel[0]?.model).toBe("real-90");
    expect(store.daily).toHaveLength(90);
    expect(store.error).toBeNull();
    expect(store.loadedOnce).toBe(true);
  });

  test("config load does not replace a draft edited after the request starts", async () => {
    const refreshConfig = deferred<Response>();
    const refreshModels = deferred<Response>();
    let configGets = 0;
    let modelGets = 0;
    globalThis.fetch = ((input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/config/models") {
        modelGets += 1;
        return modelGets === 1
          ? Promise.resolve(jsonResponse(virtualModels()))
          : refreshModels.promise;
      }
      if (path === "/api/config") {
        configGets += 1;
        return configGets === 1
          ? Promise.resolve(jsonResponse(validConfig()))
          : refreshConfig.promise;
      }
      throw new Error(`Unexpected request: ${path}`);
    }) as typeof fetch;
    const store = useConfigStore();
    await store.load();

    const refresh = store.load();
    store.draft!.server.host = "locally-edited";
    refreshConfig.resolve(jsonResponse(validConfig("remote-update")));
    refreshModels.resolve(jsonResponse(virtualModels()));
    await refresh;

    expect(store.draft?.server.host).toBe("locally-edited");
    expect(store.dirty).toBe(true);
    expect(store.error).toBeNull();
    expect(store.loading).toBe(false);
  });

  test("config save starts a post-PUT load instead of reusing a pre-save request", async () => {
    const staleConfig = deferred<Response>();
    const staleModels = deferred<Response>();
    const freshConfig = deferred<Response>();
    const freshModels = deferred<Response>();
    let configGets = 0;
    let modelGets = 0;
    let putBody: AppConfig | null = null;
    globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/api/config/models") {
        modelGets += 1;
        if (modelGets === 1) return Promise.resolve(jsonResponse(virtualModels()));
        return modelGets === 2 ? staleModels.promise : freshModels.promise;
      }
      if (path === "/api/config" && init?.method === "PUT") {
        putBody = JSON.parse(String(init.body)) as AppConfig;
        return Promise.resolve(jsonResponse({ status: "ok" }));
      }
      if (path === "/api/config") {
        configGets += 1;
        if (configGets === 1) return Promise.resolve(jsonResponse(validConfig()));
        return configGets === 2 ? staleConfig.promise : freshConfig.promise;
      }
      throw new Error(`Unexpected request: ${path}`);
    }) as typeof fetch;
    const store = useConfigStore();
    await store.load();
    store.draft!.server.host = "saved-value";

    const preSaveLoad = store.load();
    const save = store.save();
    for (let attempt = 0; attempt < 20 && configGets < 3; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 0));
    }

    expect(putBody?.server.host).toBe("saved-value");
    expect(configGets).toBe(3);
    expect(modelGets).toBe(3);
    freshConfig.resolve(jsonResponse(validConfig("saved-value")));
    freshModels.resolve(jsonResponse(virtualModels()));
    await save;

    staleConfig.resolve(jsonResponse(validConfig("stale-value")));
    staleModels.resolve(jsonResponse(virtualModels()));
    await preSaveLoad;

    expect(store.draft?.server.host).toBe("saved-value");
    expect(store.dirty).toBe(false);
    expect(store.error).toBeNull();
    expect(store.loading).toBe(false);
  });

  test("config rejects a concurrent save without sending a second PUT", async () => {
    const put = deferred<Response>();
    let putCount = 0;
    globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/api/config/models") {
        return Promise.resolve(jsonResponse(virtualModels()));
      }
      if (path === "/api/config" && init?.method === "PUT") {
        putCount += 1;
        return put.promise;
      }
      if (path === "/api/config") {
        return Promise.resolve(jsonResponse(validConfig()));
      }
      throw new Error(`Unexpected request: ${path}`);
    }) as typeof fetch;
    const store = useConfigStore();
    await store.load();
    store.draft!.server.host = "first-edit";

    const firstSave = store.save();
    store.draft!.server.host = "newer-edit";

    expect(store.saving).toBe(true);
    await expect(store.save()).rejects.toThrow("配置正在保存");
    expect(putCount).toBe(1);

    put.resolve(jsonResponse({ status: "ok" }));
    await firstSave;

    expect(store.saving).toBe(false);
    expect(store.draft?.server.host).toBe("newer-edit");
    expect(store.dirty).toBe(true);
  });
});
