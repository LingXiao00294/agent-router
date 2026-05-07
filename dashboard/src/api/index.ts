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
  provider_type: string;
  provider_model: string;
  attempt: number;
  latency_ms: number;
  status: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export interface CallsPage {
  data: CallRecord[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

export interface ModelStat {
  virtual_model: string;
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
  size = 50
): Promise<CallsPage> {
  const res = await fetch(`${BASE}/calls?page=${page}&size=${size}`);
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

export async function fetchDailyTrend(days = 30) {
  const res = await fetch(`${BASE}/metrics/daily?days=${days}`);
  return res.json();
}
