import { beforeEach, describe, expect, test } from "bun:test";
import { createPinia, setActivePinia } from "pinia";
import type { AppConfig } from "../src/api/types";
import { useConfigStore } from "../src/stores/config";

function validConfig(): AppConfig {
  return {
    server: {
      host: "127.0.0.1",
      port: 9456,
      log_level: "info",
      log_file: "",
      log_max_bytes: 0,
      log_backup_count: 0,
    },
    router: {
      failure_threshold: 5,
      recovery_timeout: 600,
      mode: "failover",
    },
    providers: {
      zai: {
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
        models: { existing: {} },
      },
    },
    models: {},
  };
}

beforeEach(() => setActivePinia(createPinia()));

describe("actual-model catalog mutations", () => {
  test("adds, edits, and removes an unreferenced actual model", () => {
    const store = useConfigStore();
    store.draft = validConfig();

    expect(store.addActualModel("zai", " glm-5 ", { input_price_per_million: 1 })).toBe(true);
    expect(store.addActualModel("zai", "glm-5", {})).toBe(false);
    expect(store.updateActualModel("zai", "glm-5", { output_price_per_million: 4 })).toBe(true);
    expect(store.draft.providers.zai.models["glm-5"]).toEqual({ output_price_per_million: 4 });

    expect(store.removeActualModel("zai", "glm-5")).toEqual([]);
    expect(store.draft.providers.zai.models["glm-5"]).toBeUndefined();
  });

  test("keeps data unchanged when an actual model is referenced", () => {
    const store = useConfigStore();
    store.draft = validConfig();
    store.models = {
      routerA: {
        pinned_model: { provider: "zai", model: "existing" },
        models: [{ provider: "zai", model: "existing" }],
      },
    };
    const before = JSON.parse(JSON.stringify(store.draft.providers.zai.models)) as Record<
      string,
      unknown
    >;

    expect(store.removeActualModel("zai", "existing")).toEqual(["routerA"]);
    expect(store.draft.providers.zai.models).toEqual(before);
  });

  test("updates an existing actual model by its exact key", () => {
    const store = useConfigStore();
    store.draft = validConfig();
    store.draft.providers.zai.models[" glm-5 "] = { input_price_per_million: 1 };

    expect(
      store.updateActualModel("zai", " glm-5 ", { output_price_per_million: 4 }),
    ).toBe(true);
    expect(store.draft.providers.zai.models[" glm-5 "]).toEqual({
      output_price_per_million: 4,
    });
    expect(store.draft.providers.zai.models["glm-5"]).toBeUndefined();
  });

  test("rejects duplicate and dangling virtual-model references during validation", () => {
    const store = useConfigStore();
    store.draft = validConfig();
    store.models = {
      routerA: {
        pinned_model: null,
        models: [
          { provider: "zai", model: "existing" },
          { provider: "zai", model: "existing" },
          { provider: "zai", model: "missing" },
        ],
      },
    };

    expect(store.validate()).toBe(false);
    expect(store.fieldErrors["models.routerA.ref.1"]).toContain("不能重复");
    expect(store.fieldErrors["models.routerA.ref.2.model"]).toContain("不存在");
  });
});
