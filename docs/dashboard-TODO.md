# Dashboard 从零重建 TODO

> 目标：在**不含旧 dashboard 前端**的干净分支上，按本文档从零实现监控面板。  
> 后端 API **不改**；契约来自 `src/agent_router/`（以代码为准）。  
> 核对日期：2026-07-10  
> Router 默认基址：`http://127.0.0.1:9456`

---

## 0. 开工前约定

- [x] 从主分支拉新分支（如 `feat/dashboard-v2`），清空旧 `dashboard/src`（或整目录重建）
- [x] **不要**复用旧 UI；只按本文档的 API + 功能清单实现
- [x] 包管理：`bun`；后端：`uv`
- [x] 开发：`uv run agent-router serve` + `cd dashboard && bun run dev`
- [x] 生产：`bun run build` → `dashboard/dist/`，再 `uv run agent-router dashboard`

### 工程约束

| 项 | 说明 |
|---|---|
| 构建产物 | 必须有 `dashboard/dist/index.html`；`find_dashboard_dist()` 会查找 |
| Vite 代理 | `/api`、`/health`、`/v1` → `127.0.0.1:${ROUTER_PORT\|\|9456}`（见 `dashboard/vite.config.ts`） |
| 独立面板 | `agent-router dashboard` 反代 `/health`、`/api/*`、`/v1/*` 到 `--router-url`，其余走 SPA |
| 鉴权 | **无**；勿加登录假设 |
| 请求头 | 可选透传 `X-Request-ID`（字母数字 `-_`，≤128）；响应会回写同名头 |

---

## 1. Router HTTP API 总表（完整清单）

以下为 **agent-router serve** 暴露的全部 HTTP 接口（共 **16** 个）。  
独立 dashboard 进程不新增业务 API，只反代其中 `/health`、`/api/*`、`/v1/*`。

| # | 方法 | 路径 | Dashboard 用途 | 源码 |
|---|---|---|---|---|
| 1 | `GET` | `/health` | 探活 / 连接状态 | `app.py` |
| 2 | `GET` | `/api/metrics/summary` | Overview KPI | `api/metrics.py` |
| 3 | `GET` | `/api/metrics/by-model` | 按虚拟模型统计 | `api/metrics.py` |
| 4 | `GET` | `/api/metrics/by-real-model` | 按真实模型统计 / 图表 | `api/metrics.py` |
| 5 | `GET` | `/api/metrics/by-provider` | 按 provider_type 统计 | `api/metrics.py` |
| 6 | `GET` | `/api/metrics/daily` | 日趋势图 | `api/metrics.py` |
| 7 | `GET` | `/api/calls` | 调用列表 | `api/metrics.py` |
| 8 | `GET` | `/api/calls/{call_id}` | 调用详情 | `api/metrics.py` |
| 9 | `GET` | `/api/config` | 配置编辑主数据源 | `api/config.py` |
| 10 | `GET` | `/api/config/providers` | Provider 摘要（可选） | `api/config.py` |
| 11 | `GET` | `/api/config/models` | 虚拟模型规范化结构 | `api/config.py` |
| 12 | `PUT` | `/api/config` | 保存配置并热重载 | `api/config.py` |
| 13 | `GET` | `/api/circuit-breaker` | 熔断状态 | `app.py` |
| 14 | `POST` | `/api/circuit-breaker/{provider}/reset` | 重置熔断 | `app.py` |
| 15 | `GET` | `/v1/models` | 虚拟模型列表（Anthropic 形，可选） | `app.py` |
| 16 | `POST` | `/v1/messages` | **LLM 客户端接口**；面板一般不调用 | `app.py` |

核对清单（实现前勾选，确保无遗漏）：

- [x] #1 `/health`
- [x] #2–#6 metrics 五端点
- [x] #7–#8 calls
- [x] #9–#12 config
- [x] #13–#14 circuit-breaker
- [ ] #15 `/v1/models`（可选展示）
- [x] #16 `/v1/messages`（文档知晓即可，UI 不做聊天）

---

## 2. 通用约定

### 2.1 调用方式

- 浏览器一律用**相对路径**（`/api/...`），由 Vite 或 dashboard 反代转发。
- 建议 `fetch` 封装：默认超时 **30s**；独立 dashboard 反代上游超时约 **60s**。
- JSON：`Content-Type: application/json`（PUT/POST body）。

### 2.2 错误体

多数管理 API（metrics/config/circuit）使用 FastAPI 风格：

```json
{ "detail": "错误说明字符串" }
```

校验失败时 `detail` 也可能是数组。  
`/v1/messages` 失败多用 Anthropic 风格：

```json
{ "error": { "type": "...", "message": "..." } }
```

并可能带 `Retry-After`（429/503）。

### 2.3 TypeScript 类型总览（建议）

```ts
// --- metrics ---
interface Summary {
  total_calls: number;
  success_count: number;
  error_count: number;
  success_rate: number; // 0–100 百分数，勿再 *100
  total_input_tokens: number;
  total_output_tokens: number;
  total_cache_read: number;
  total_cache_write: number;
  total_cost_usd: number;
  avg_latency_ms: number;
}

interface ModelStatVirtual {
  virtual_model: string;
  count: number;
  success_count: number;
  total_input_tokens: number | null;
  total_output_tokens: number | null;
  total_cost_usd: number | null;
}

interface ModelStatReal {
  model: string;
  count: number;
  success_count: number;
  total_input_tokens: number | null;
  total_output_tokens: number | null;
  total_cost_usd: number | null;
}

interface ProviderStat {
  provider: string; // 来自 provider_type，可能 "unknown"
  count: number;
  success_count: number;
}

interface DailyStat {
  day: string; // YYYY-MM-DD，SQLite DATE(timestamp) → UTC
  count: number;
  success_count: number;
  cost_usd: number | null;
}

interface FailoverEntry {
  provider: string;
  model: string;
  error: string;
  latency_ms?: number;
}

interface CallRecord {
  id: string;
  timestamp: string; // UTC ISO
  virtual_model: string;
  provider_name: string | null;
  provider_type: string | null;
  provider_model: string | null;
  provider_url: string | null;
  attempt: number;
  latency_ms: number | null;
  request_body: string | null;   // JSON 字符串
  request_tokens: number | null;
  status: string;                // 常见 "success" | "error"
  error_type: string | null;
  error_message: string | null;
  response_body: string | null;  // JSON 字符串
  input_tokens: number | null;
  output_tokens: number | null;
  cache_read_tokens: number | null;
  cache_write_tokens: number | null;
  cost_usd: number | null;
  failover_details: string | null; // JSON 字符串 → FailoverEntry[]
}

interface CallsPage {
  data: CallRecord[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

// --- config ---
type RouterMode = "failover" | "sticky";
type ProviderType = "anthropic" | "openai";
type LogLevel = "debug" | "info" | "warning" | "error";

interface ServerConfig {
  host: string;
  port: number;
  log_level: LogLevel;
  log_file: string;
  log_max_bytes: number;
  log_backup_count: number;
}

interface RouterConfig {
  failure_threshold: number;
  recovery_timeout: number;
  mode: RouterMode;
}

interface ProviderConfig {
  type: ProviderType;
  api_key: string;
  base_url: string;
  timeout_seconds: number;
  failure_threshold?: number | null;
  recovery_timeout?: number | null;
  max_concurrent?: number;
  max_queue?: number;
  queue_wait_timeout?: number;
  rate_limit_cooldown?: number;
  // GET 时附加：
  has_key?: boolean;
  api_key_unresolved?: boolean;
}

interface ModelRef {
  provider: string;
  model: string;
  priority: number;
}

interface VirtualModelConfig {
  pinned_provider?: string | null;
  pinned_model?: string | null;
  providers: ModelRef[];
}

interface AppConfig {
  server: ServerConfig;
  router: RouterConfig;
  providers: Record<string, ProviderConfig>;
  // GET /api/config 可能仍是旧 list 或新 object；PUT 建议统一新格式
  models: Record<string, VirtualModelConfig | ModelRef[]>;
}

type CircuitState = "closed" | "open" | "half_open";
```

---

## 3. 各接口详细说明

### 3.1 `GET /health`

**用途**：探活。  
**响应 200**：

```json
{ "status": "ok" }
```

```bash
curl -s http://127.0.0.1:9456/health
```

- [x] 面板可显示「后端已连接 / 断开」

---

### 3.2 `GET /api/metrics/summary`

**用途**：Overview KPI。  
**响应 200**：

```json
{
  "total_calls": 120,
  "success_count": 110,
  "error_count": 10,
  "success_rate": 91.67,
  "total_input_tokens": 100000,
  "total_output_tokens": 50000,
  "total_cache_read": 2000,
  "total_cache_write": 100,
  "total_cost_usd": 1.234567,
  "avg_latency_ms": 850
}
```

| 字段 | 含义 |
|---|---|
| `success_rate` | **已是 0–100 百分数**（`round(success/total*100, 2)`） |
| `avg_latency_ms` | 仅对 `status=success` 求平均后四舍五入 |
| token / cost | 库内 SUM，空则 0 |

```bash
curl -s http://127.0.0.1:9456/api/metrics/summary
```

- [x] 展示总调用、成功率、Token、费用、延迟、Cache

---

### 3.3 `GET /api/metrics/by-model`

**用途**：按**虚拟模型** `virtual_model` 分组。  
**响应 200**：`ModelStatVirtual[]`

```json
[
  {
    "virtual_model": "opus-router",
    "count": 40,
    "success_count": 38,
    "total_input_tokens": 1000,
    "total_output_tokens": 500,
    "total_cost_usd": 0.12
  }
]
```

```bash
curl -s http://127.0.0.1:9456/api/metrics/by-model
```

- [x] Overview 可选图表 / 表格

---

### 3.4 `GET /api/metrics/by-real-model`

**用途**：按真实模型 `provider_model` 分组（`WHERE provider_model IS NOT NULL`）。  
**响应 200**：`ModelStatReal[]`（字段名是 `model` 不是 `virtual_model`）

```json
[
  {
    "model": "deepseek-v4-pro",
    "count": 20,
    "success_count": 19,
    "total_input_tokens": 800,
    "total_output_tokens": 400,
    "total_cost_usd": 0.05
  }
]
```

```bash
curl -s http://127.0.0.1:9456/api/metrics/by-real-model
```

- [x] Overview 主图表数据源（分布 / Token 堆叠）

---

### 3.5 `GET /api/metrics/by-provider`

**用途**：按 `provider_type` 分组；空则显示为 `unknown`。  
**响应 200**：`ProviderStat[]`

```json
[
  { "provider": "anthropic", "count": 100, "success_count": 95 }
]
```

```bash
curl -s http://127.0.0.1:9456/api/metrics/by-provider
```

- [x] Overview 可选展示

---

### 3.6 `GET /api/metrics/daily`

**Query**：

| 参数 | 类型 | 默认 | 约束 |
|---|---|---|---|
| `days` | int | `30` | `ge=1, le=365` |

**响应 200**：`DailyStat[]`，按 `day` 升序。  
`day` 来自 `DATE(timestamp)`（SQLite，与写入的 UTC ISO 对齐 → **按 UTC 日**）。

```json
[
  { "day": "2026-07-01", "count": 10, "success_count": 9, "cost_usd": 0.01 },
  { "day": "2026-07-03", "count": 5, "success_count": 5, "cost_usd": 0.02 }
]
```

**前端**：无数据的日期需补 `count/success_count/cost_usd = 0`，否则折线/柱图会断档。建议切换 7 / 30 / 90。

```bash
curl -s 'http://127.0.0.1:9456/api/metrics/daily?days=30'
```

- [x] 趋势图 + 天数切换；UTC 补日

---

### 3.7 `GET /api/calls`

**Query**：

| 参数 | 类型 | 默认 | 约束 | 说明 |
|---|---|---|---|---|
| `page` | int | `1` | ≥1 | |
| `size` | int | `50` | 1–200 | |
| `model` | string? | — | 等值 | 过滤 `virtual_model` |
| `status` | string? | — | 等值 | 过滤 `status`（如 `success` / `error`） |

**响应 200**：

```json
{
  "data": [ /* CallRecord，见 §3.8 字段表 */ ],
  "total": 120,
  "page": 1,
  "size": 50,
  "pages": 3
}
```

`pages = max(1, ceil(total/size))`。排序：`timestamp DESC`。

```bash
curl -s 'http://127.0.0.1:9456/api/calls?page=1&size=50'
curl -s 'http://127.0.0.1:9456/api/calls?model=opus-router&status=error'
```

- [x] 分页表、筛选、URL query 同步（建议）

---

### 3.8 `GET /api/calls/{call_id}`

**路径**：`call_id` 为记录 UUID。  
**响应 200**：单个 `CallRecord`（与列表元素同结构，含 body 字段）。  
**响应 404**：

```json
{ "detail": "call not found" }
```

#### CallRecord 全字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | UUID |
| `timestamp` | string | UTC ISO（写入时 `datetime.now(timezone.utc).isoformat()`） |
| `virtual_model` | string | |
| `provider_name` | string\|null | 配置中的 provider 名 |
| `provider_type` | string\|null | 如 `anthropic` |
| `provider_model` | string\|null | 上游真实模型 |
| `provider_url` | string\|null | base_url |
| `attempt` | number | 第几次尝试；`>1` 表示经历过 failover |
| `latency_ms` | number\|null | |
| `status` | string | 常见 `success` / `error` |
| `error_type` | string\|null | 如 `unknown_model`、`rate_limit_error`、`all_providers_failed`… |
| `error_message` | string\|null | |
| `request_body` | string\|null | **JSON 文本**（已 stringify） |
| `response_body` | string\|null | **JSON 文本** |
| `request_tokens` | number\|null | 请求体字符估算 |
| `input_tokens` | number\|null | |
| `output_tokens` | number\|null | |
| `cache_read_tokens` | number\|null | 对应 usage `cache_read_input_tokens` |
| `cache_write_tokens` | number\|null | 对应 usage `cache_creation_input_tokens` |
| `cost_usd` | number\|null | |
| `failover_details` | string\|null | **JSON 文本** → `FailoverEntry[]` |

#### `failover_details` 解析示例

```json
[
  { "provider": "zai", "model": "glm-5.2", "error": "429 ...", "latency_ms": 120 }
]
```

详情 UI：逐步展示失败项，再追加当前成功命中的 provider/model。

```bash
curl -s http://127.0.0.1:9456/api/calls/<id>
```

- [x] 详情面板：元数据、failover 链、错误、格式化 JSON（长 content 可截断）

---

### 3.9 `GET /api/config`

**用途**：配置页主数据；读磁盘 `config.toml`，对每个 provider 的 `api_key` 脱敏并附加字段。

**脱敏规则**（`_mask_key`）：长度 ≤8 则全 `*`；否则 `前4 + 中间* + 后4`。  
同时写入：

| 附加字段 | 含义 |
|---|---|
| `has_key` | expandvars 后非空且无未解析 `${ENV}` |
| `api_key_unresolved` | 仍含 `${...}` |
| `api_key` | 未解析时返回 `""`；否则返回脱敏串 |

**响应 200 结构示例**：

```json
{
  "server": {
    "host": "127.0.0.1",
    "port": 9456,
    "log_level": "info",
    "log_file": "logs/agent-router.log",
    "log_max_bytes": 10000000,
    "log_backup_count": 5
  },
  "router": {
    "failure_threshold": 5,
    "recovery_timeout": 600,
    "mode": "failover"
  },
  "providers": {
    "zai": {
      "type": "anthropic",
      "api_key": "sk-a****xyz",
      "has_key": true,
      "api_key_unresolved": false,
      "base_url": "https://api.z.ai/api/anthropic",
      "timeout_seconds": 120,
      "max_concurrent": 0,
      "max_queue": 0,
      "queue_wait_timeout": 30,
      "rate_limit_cooldown": 30
    }
  },
  "models": {
    "opus-router": {
      "pinned_provider": null,
      "pinned_model": null,
      "providers": [
        { "provider": "zai", "model": "glm-5.2", "priority": 1 }
      ]
    }
  }
}
```

**注意**：磁盘上旧格式可能是 `models.x = [ {provider, model, priority}, ... ]`（纯 list）。GET 原样返回 TOML 解析结果；编辑时建议用 §3.11 的规范化结果，PUT 时统一写成新 object 格式。

```bash
curl -s http://127.0.0.1:9456/api/config
```

- [x] 加载进编辑态；api_key 勿当真实密钥展示/回传（除非用户新输入）

---

### 3.10 `GET /api/config/providers`

**用途**：仅 providers 摘要（字段比全量少）。  
**响应 200**：

```json
{
  "zai": {
    "type": "anthropic",
    "base_url": "https://api.z.ai/api/anthropic",
    "timeout_seconds": 120.0,
    "api_key": "sk-a****xyz",
    "has_key": true,
    "api_key_unresolved": false
  }
}
```

**不含**限流/熔断覆盖字段（那些在 `GET /api/config`）。面板编辑应以 **`GET /api/config` 为准**；本接口可选用于轻量列表。

```bash
curl -s http://127.0.0.1:9456/api/config/providers
```

- [ ] 可选：快速列表；完整编辑仍用 `/api/config`

---

### 3.11 `GET /api/config/models`

**用途**：虚拟模型**规范化**视图（推荐配置页模型区使用）。

- 兼容旧 list / 新 object
- `providers` 按 `priority` 升序
- 抽出 `pinned_provider` / `pinned_model`

**响应 200**：

```json
{
  "opus-router": {
    "pinned_provider": "zai",
    "pinned_model": "glm-5.2",
    "providers": [
      { "provider": "zai", "model": "glm-5.2", "priority": 1 },
      { "provider": "deepseek", "model": "deepseek-v4-pro", "priority": 2 }
    ]
  }
}
```

```bash
curl -s http://127.0.0.1:9456/api/config/models
```

- [x] 与 `GET /api/config` 并行加载模型编辑态（旧前端即如此）

---

### 3.12 `PUT /api/config`

**用途**：全量写回 `config.toml` + 热重载 Router / 日志。  
**请求头**：`Content-Type: application/json`  
**Body**：建议始终提交完整四段：

```json
{
  "server": {
    "host": "127.0.0.1",
    "port": 9456,
    "log_level": "info",
    "log_file": "logs/agent-router.log",
    "log_max_bytes": 10000000,
    "log_backup_count": 5
  },
  "router": {
    "failure_threshold": 5,
    "recovery_timeout": 600,
    "mode": "failover"
  },
  "providers": {
    "zai": {
      "type": "anthropic",
      "api_key": "",
      "base_url": "https://api.z.ai/api/anthropic",
      "timeout_seconds": 120,
      "failure_threshold": null,
      "recovery_timeout": null,
      "max_concurrent": 0,
      "max_queue": 0,
      "queue_wait_timeout": 30,
      "rate_limit_cooldown": 30
    }
  },
  "models": {
    "opus-router": {
      "pinned_provider": null,
      "pinned_model": null,
      "providers": [
        { "provider": "zai", "model": "glm-5.2", "priority": 1 }
      ]
    }
  }
}
```

#### 服务端语义（必须遵守）

1. **缺段合并**：body 缺少 `server` / `router` / `providers` / `models` 任一键时，用磁盘已有段填充，防止误删。
2. **api_key 保护**：若值为空、`${PLACEHOLDER}`、全 `*`、或「前4+*+后4」脱敏形态 → **保留原文件中的 key**。  
   - 新建 provider 只交脱敏/空 key → **400**（`新建 provider 'x' 需要提供有效的 api_key`）。
3. **models 写入**：`providers` 为空的模型**不会写入** TOML（避免热重载因空模型失败）。
4. **priority**：前端应按数组顺序写成 `1..n`（不要依赖用户手填乱序）。
5. **pinned_***：仅当仍匹配链中某项时写入；成对出现。
6. 写盘成功后调用热重载；配置语义无效会 **500**（`配置已写入但热重载失败: ...` 或写入失败信息）。

**成功 200**：

```json
{ "status": "ok", "message": "配置已更新并热重载" }
```

**失败**：`4xx/5xx` + `{ "detail": "..." }`

```bash
curl -s -X PUT http://127.0.0.1:9456/api/config \
  -H 'Content-Type: application/json' \
  -d @config-body.json
```

#### Provider 字段约束（与 `ProviderDef` 一致）

| 字段 | 约束 |
|---|---|
| `type` | `anthropic` \| `openai` |
| `api_key` | 逻辑必填；保存时空/脱敏=保留旧值 |
| `base_url` | 非空；服务端会去尾 `/` |
| `timeout_seconds` | 默认 120；前端校验 >0 |
| `failure_threshold` | `null`=用全局；整数 |
| `recovery_timeout` | `null`=用全局 |
| `max_concurrent` | ≥0；**0=不限** |
| `max_queue` | ≥0；**0=不排队** |
| `queue_wait_timeout` | >0；默认 30 |
| `rate_limit_cooldown` | >0；默认 30 |

#### Server / Router 字段

| 段 | 字段 | 说明 |
|---|---|---|
| server | `host` | 默认 `127.0.0.1` |
| server | `port` | 默认 9456；1–65535 |
| server | `log_level` | `debug`\|`info`\|`warning`\|`error` |
| server | `log_file` | 空字符串=仅 stdout |
| server | `log_max_bytes` | 默认 10000000 |
| server | `log_backup_count` | 默认 5 |
| router | `failure_threshold` | 默认 5；≥0 |
| router | `recovery_timeout` | 默认 600（秒）；>0 |
| router | `mode` | `failover` \| `sticky` |

- [x] Dirty 检测、校验、保存、成功/失败 toast
- [x] 顶栏改 mode：**立即 PUT**；配置页改 mode：可等点保存

---

### 3.13 `GET /api/circuit-breaker`

**用途**：所有已知 provider 的熔断状态。  
**响应 200**：

```json
{
  "zai": "closed",
  "deepseek": "open",
  "mimo token plan": "half_open"
}
```

| 值 | 含义 | UI |
|---|---|---|
| `closed` | 正常 | 成功色 |
| `open` | 已熔断 | 危险色；可 Reset |
| `half_open` | 半开探测 | 警告色；可 Reset |

说明：连续 5xx/连接失败达阈值 → open；401/403 → **立即 open 且不自动恢复**，必须 reset。429/限流走短冷却，**不计入**熔断计数。

```bash
curl -s http://127.0.0.1:9456/api/circuit-breaker
```

- [x] Overview 告警 + 配置页熔断面板

---

### 3.14 `POST /api/circuit-breaker/{provider}/reset`

**路径**：`provider` 为 provider **名称**（与配置键一致，可含空格；URL 需 encode）。  
**Body**：无。  
**响应 200**：

```json
{ "status": "ok", "provider": "deepseek" }
```

```bash
curl -s -X POST \
  'http://127.0.0.1:9456/api/circuit-breaker/deepseek/reset'
curl -s -X POST \
  --path-as-is \
  'http://127.0.0.1:9456/api/circuit-breaker/mimo%20token%20plan/reset'
```

- [x] 仅非 `closed` 显示重置；成功后刷新状态列表

---

### 3.15 `GET /v1/models`

**用途**：Anthropic List Models 兼容；列出当前虚拟模型名。  
**响应 200**：

```json
{
  "data": [
    {
      "id": "opus-router",
      "type": "model",
      "display_name": "opus-router",
      "created_at": "2025-01-01T00:00:00Z"
    }
  ]
}
```

`created_at` 目前为占位常量。配置编辑请用 `/api/config/models`。

```bash
curl -s http://127.0.0.1:9456/api/../v1/models
# 或
curl -s http://127.0.0.1:9456/v1/models
```

- [ ] 可选：只读展示已注册虚拟模型

---

### 3.16 `POST /v1/messages`（面板不实现 UI，但需知晓）

**用途**：LLM 客户端主入口（Anthropic Messages 兼容）。  
**Body**：标准 Messages JSON；必填逻辑字段含 `model`（虚拟模型名）、`messages` 等；`stream: true|false`。

| 场景 | HTTP | 形态 |
|---|---|---|
| 非流式成功 | 200 | 上游 Messages JSON |
| 流式成功 | 200 | `text/event-stream` |
| 未知模型 | 400 | `{ "error": { "type": "invalid_request_error", "message": "..." } }` |
| 全失败 | 502 | `{ "error": { "type": "api_error", "message": "..." } }` |
| 限流无可用 | 429 | `rate_limit_error`；可能 `Retry-After` |
| 容量不足 | 503 | `overloaded_error`；可能 `Retry-After` |

成功/失败都会写入 `calls` 表，供 metrics/calls API 查询——**面板通过读 API 观察结果，而不是自己调 messages**。

- [x] 文档知晓；**不做**面板内聊天

---

## 4. 独立 Dashboard 反代行为（`dashboard.py`）

| 路径 | 行为 |
|---|---|
| `/health` | 反代到 router |
| `/api/{path}` | 反代（含全部 config/metrics/calls/circuit-breaker） |
| `/v1/{path}` | 反代（含 models/messages；messages 流式会透传 SSE） |
| 其它 GET | 静态文件或 `index.html` SPA fallback |

反代连不上 router → **502** + `detail` 说明检查 `--router-url`。

---

## 5. 功能清单（按页面）

### 5.1 壳与全局

- [x] 导航覆盖：监控 Overview / 调用 Calls / 配置 Config（子页自定）
- [x] 主题：浅色默认；建议深色可切换（localStorage）
- [x] 全局 Failover/Sticky：改 `router.mode` 后 **立即 PUT `/api/config`**；失败回滚；`config` 未就绪禁用
- [x] 手动刷新 + 自动刷新（建议 5/10/30/60s；`document.hidden` 时暂停）
- [x] Toast、危险操作确认、未保存离开确认
- [x] 建议快捷键：`R` 刷新；`Ctrl/Cmd+S` 保存；筛选聚焦

### 5.2 Overview（读 API：#1–#6, #13）

- [x] KPI（#2 summary）
- [x] 熔断告警（#13），链到熔断管理
- [x] 日趋势（#6）+ 补日
- [x] 真实模型图（#4）；可选 #3/#5
- [x] loading / error / empty；静默刷新不闪烁

### 5.3 Calls（#7–#8）

- [x] 分页表：时间、虚拟模型、Provider、真实模型、状态、延迟、Token、Cache、费用
- [x] `attempt > 1` 标记 failover
- [x] 筛选 `model` + `status`（对接 query）
- [x] 详情：字段全集 + failover 链 + JSON
- [x] 空态区分无数据 / 筛选无结果

### 5.4 Config（#9–#14）

#### Server

- [x] 编辑全部 server 字段；port/host 校验

#### Router

- [x] `mode` / `failure_threshold` / `recovery_timeout`
- [x] 页内改 mode 可只标 dirty（与顶栏立即保存区分）

#### Circuit breaker

- [x] 列表 #13；Reset #14；刷新

#### Providers

- [x] CRUD；限流四字段 + 可选熔断覆盖
- [x] `has_key` 占位「留空保留」；保存遵守脱敏规则
- [x] 删除确认 + 级联清理模型 refs/pin

#### Virtual models

- [x] CRUD；链顺序 = priority
- [x] 拖拽或上下移
- [x] Sticky：pin 必须在链上；Failover：pin UI 可禁用但仍可保留数据
- [x] 校验：名唯一、至少一条 ref、sticky 时 pin 有效

#### 横切

- [x] Dirty、Ctrl+S、保存 toast、字段错误、加载失败重试
- [x] 建议并行：`GET /api/config` + `GET /api/config/models`（+ 可选 providers）

---

## 6. 建议实现顺序

1. [x] 脚手架 + API client（覆盖 §1 总表类型）
2. [x] `#1` health + `#2` summary + `#7` calls 列表
3. [x] Overview：`#4` `#6` `#13`
4. [x] Calls 详情 `#8` + 筛选
5. [x] Config 只读 `#9` `#11`（`#10` 可选）
6. [x] Config 保存 `#12`（Server/Router → Providers/Models）
7. [x] 顶栏 mode 即时 `#12` + 熔断 `#14`
8. [x] 自动刷新、主题、空错态
9. [x] `bun run build` + `agent-router dashboard` 联调
10. [x] （可选）`#15` 展示；确认不调用 `#16`

---

## 7. 验收清单

- [x] §1 总表 16 个接口均已文档化；面板实现覆盖除 `#16` 外全部「Dashboard 用途」列
- [x] `success_rate` 按 0–100 显示正确
- [x] 日趋势 UTC 补日正确
- [x] PUT 不会用空/脱敏 key 清掉密钥；新建 provider 必须真 key
- [x] Sticky / Failover + pinned 行为正确
- [x] 熔断 reset 可用
- [x] Vite 开发代理与 `agent-router dashboard` 生产反代均可工作
- [x] UI 为新设计，非旧面板换皮

---

## 8. 参考源码

| 主题 | 路径 |
|---|---|
| Metrics / Calls | `src/agent_router/api/metrics.py` |
| Config | `src/agent_router/api/config.py` |
| Health / CB / v1 | `src/agent_router/app.py` |
| DB schema / 聚合 | `src/agent_router/db.py` |
| 配置 Pydantic | `src/agent_router/config.py` |
| 熔断 | `src/agent_router/circuit_breaker.py` |
| Dashboard 反代 | `src/agent_router/dashboard.py` |
| Vite 代理 | `dashboard/vite.config.ts` |
| 示例 TOML | `config.toml.example` |
| README API 表 | `README.md`（「API」小节） |

---

## 9. 明确不做

- [x] 修改后端 API / 加鉴权
- [x] 面板内调用 `#16 POST /v1/messages` 做聊天
- [x] 以旧 dashboard UI 代码为起点（可丢弃旧前端分支）
