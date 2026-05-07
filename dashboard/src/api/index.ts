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
