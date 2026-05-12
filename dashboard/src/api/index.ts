const BASE = "/api";

export interface Summary {
  total_calls: number;
  success_count: number;
  error_count: number;
  success_rate: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cache_read: number;
  total_cache_write: number;
  total_cost_usd: number;
  avg_latency_ms: number;
}

export interface FailoverEntry {
  provider: string;
  model: string;
  error: string;
  latency_ms?: number;
}

export interface CallRecord {
  id: string;
  timestamp: string;
  virtual_model: string;
  provider_name: string | null;
  provider_type: string | null;
  provider_model: string | null;
  provider_url: string | null;
  attempt: number;
  latency_ms: number | null;
  status: string;
  input_tokens: number | null;
  output_tokens: number | null;
  cache_read_tokens: number | null;
  cache_write_tokens: number | null;
  cost_usd: number | null;
  error_type: string | null;
  error_message: string | null;
  request_body: string | null;
  response_body: string | null;
  request_tokens: number | null;
  failover_details: string | null;
}

export interface CallsPage {
  data: CallRecord[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

export interface ModelStat {
  model?: string;
  virtual_model?: string;
  count: number;
  success_count: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cache_read: number;
  total_cache_write: number;
  total_cost_usd: number;
}

export async function fetchSummary(): Promise<Summary> {
  const res = await fetch(`${BASE}/metrics/summary`);
  return res.json();
}

export async function fetchCalls(
  page = 1,
  size = 50,
  model = ""
): Promise<CallsPage> {
  const params = new URLSearchParams({ page: String(page), size: String(size) });
  if (model) params.set("model", model);
  const res = await fetch(`${BASE}/calls?${params}`);
  return res.json();
}

export async function fetchCallDetail(id: string): Promise<CallRecord> {
  const res = await fetch(`${BASE}/calls/${id}`);
  return res.json();
}

export async function fetchByModel(): Promise<ModelStat[]> {
  const res = await fetch(`${BASE}/metrics/by-model`);
  return res.json();
}

export async function fetchByRealModel(): Promise<ModelStat[]> {
  const res = await fetch(`${BASE}/metrics/by-real-model`);
  return res.json();
}

export async function fetchDailyTrend(days = 30) {
  const res = await fetch(`${BASE}/metrics/daily?days=${days}`);
  return res.json();
}

export async function fetchConfig(): Promise<any> {
  const res = await fetch(`${BASE}/config`);
  return res.json();
}

export async function fetchConfigModels(): Promise<any> {
  const res = await fetch(`${BASE}/config/models`);
  return res.json();
}

export async function updateConfig(body: any): Promise<any> {
  const res = await fetch(`${BASE}/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json();
    throw new Error(data.detail || "保存失败");
  }
  return res.json();
}

export async function fetchCircuitBreakerStates(): Promise<Record<string, string>> {
  const res = await fetch(`${BASE}/circuit-breaker`);
  return res.json();
}

export async function resetCircuitBreaker(provider: string): Promise<any> {
  const res = await fetch(`${BASE}/circuit-breaker/${encodeURIComponent(provider)}/reset`, {
    method: "POST",
  });
  if (!res.ok) {
    const data = await res.json();
    throw new Error(data.detail || "重置失败");
  }
  return res.json();
}
