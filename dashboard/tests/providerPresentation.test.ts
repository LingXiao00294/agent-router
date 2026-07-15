import { describe, expect, test } from "bun:test";
import { summarizeProviderModels } from "../src/utils/providerPresentation";

describe("summarizeProviderModels", () => {
  test("limits visible models and reports the remaining count", () => {
    const summary = summarizeProviderModels(
      {
        alpha: {},
        beta: {},
        gamma: {},
        delta: {},
        epsilon: {},
      },
      3,
    );

    expect(summary).toEqual({
      visible: ["alpha", "beta", "gamma"],
      remaining: 2,
      total: 5,
    });
  });

  test("handles empty catalogs and non-positive limits", () => {
    expect(summarizeProviderModels({})).toEqual({ visible: [], remaining: 0, total: 0 });
    expect(summarizeProviderModels({ alpha: {} }, -1)).toEqual({
      visible: [],
      remaining: 1,
      total: 1,
    });
  });
});
