export interface ProviderModelSummary {
  visible: string[];
  remaining: number;
  total: number;
}

/** Keep provider cards compact while preserving the configured model order. */
export function summarizeProviderModels(
  models: Record<string, unknown>,
  limit = 4,
): ProviderModelSummary {
  const names = Object.keys(models);
  const safeLimit = Math.max(0, Math.floor(limit));
  return {
    visible: names.slice(0, safeLimit),
    remaining: Math.max(0, names.length - safeLimit),
    total: names.length,
  };
}
