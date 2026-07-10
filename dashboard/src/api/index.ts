import { request } from "./request";

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
  total_cost_usd: number;
}

export interface ProviderStat {
  provider: string;
  count: number;
  success_count: number;
}

export interface DailyStat {
  day: string;
  count: number;
  success_count: number;
  cost_usd: number;
}

export interface ServerConfig {
  host: string;
  port: number;
  log_level: string;
  log_file: string;
  log_max_bytes: number;
  log_backup_count: number;
}

export interface RouterConfig {
  failure_threshold: number;
  recovery_timeout: number;
  mode: "failover" | "sticky";
}

export interface ProviderConfig {
  type: string;
  base_url: string;
  api_key: string;
  timeout_seconds: number;
  has_key?: boolean;
  failure_threshold?: number | null;
  recovery_timeout?: number | null;
  max_concurrent?: number;
  max_queue?: number;
  queue_wait_timeout?: number;
  rate_limit_cooldown?: number;
}

export interface ModelRef {
  provider: string;
  model: string;
  priority: number;
}

export interface VirtualModelConfig {
  pinned_provider?: string | null;
  pinned_model?: string | null;
  providers: ModelRef[];
}

export interface AppConfig {
  server: ServerConfig;
  router: RouterConfig;
  providers: Record<string, ProviderConfig>;
  models: Record<string, VirtualModelConfig | ModelRef[]>;
}

export interface CircuitBreakerState {
  status: "ok";
  provider: string;
}

export function fetchSummary(): Promise<Summary> {
  return request<Summary>(`${BASE}/metrics/summary`);
}

export function fetchCalls(
  page = 1,
  size = 50,
  model = "",
  status = ""
): Promise<CallsPage> {
  const params = new URLSearchParams({ page: String(page), size: String(size) });
  if (model) params.set("model", model);
  if (status) params.set("status", status);
  return request<CallsPage>(`${BASE}/calls?${params}`);
}

export function fetchCallDetail(id: string): Promise<CallRecord> {
  return request<CallRecord>(`${BASE}/calls/${encodeURIComponent(id)}`);
}

export function fetchByModel(): Promise<ModelStat[]> {
  return request<ModelStat[]>(`${BASE}/metrics/by-model`);
}

export function fetchByRealModel(): Promise<ModelStat[]> {
  return request<ModelStat[]>(`${BASE}/metrics/by-real-model`);
}

export function fetchByProvider(): Promise<ProviderStat[]> {
  return request<ProviderStat[]>(`${BASE}/metrics/by-provider`);
}

export function fetchDailyTrend(days = 30): Promise<DailyStat[]> {
  return request<DailyStat[]>(`${BASE}/metrics/daily?days=${days}`);
}

export function fetchConfig(): Promise<AppConfig> {
  return request<AppConfig>(`${BASE}/config`);
}

export function fetchConfigModels(): Promise<Record<string, VirtualModelConfig>> {
  return request<Record<string, VirtualModelConfig>>(`${BASE}/config/models`);
}

export function updateConfig(body: AppConfig): Promise<{ status: string; message: string }> {
  return request<{ status: string; message: string }>(`${BASE}/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function fetchCircuitBreakerStates(): Promise<Record<string, string>> {
  return request<Record<string, string>>(`${BASE}/circuit-breaker`);
}

export function resetCircuitBreaker(provider: string): Promise<CircuitBreakerState> {
  return request<CircuitBreakerState>(
    `${BASE}/circuit-breaker/${encodeURIComponent(provider)}/reset`,
    { method: "POST" }
  );
}

export function fetchModels(): Promise<{ data: { id: string; type: string; display_name: string; created_at: string }[] }> {
  return request("/v1/models");
}
