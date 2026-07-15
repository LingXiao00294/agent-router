# Agent-Router 设计文档

## 概述

本地 LLM API 路由代理。Claude Code 的 `ANTHROPIC_BASE_URL` 指向本地 router，虚拟模型名映射到多个真实 provider，按优先级路由，故障时自动转移到下一优先级。

```
Claude Code → router (本地 FastAPI) → Anthropic API   (优先级 1)
                                    → 智谱 API       (优先级 2, 故障转移)
                                    → OpenAI API      (优先级 3, 协议转换 + 故障转移)
```

---

## 项目结构

```
agent-router/
├── pyproject.toml                  # 项目元数据 + 依赖
├── config.toml                     # 路由配置 (用户编辑)
├── docs/
│   └── design.md                   # 本文档
├── src/agent_router/
│   ├── __init__.py
│   ├── main.py                     # 入口: argparse + uvicorn
│   ├── app.py                      # FastAPI 应用 + 路由处理器
│   ├── config.py                   # TOML 加载 + ${ENV_VAR} 插值 + Pydantic 校验
│   ├── routing.py                  # 核心: 优先级链 + 故障转移 + 熔断
│   ├── circuit_breaker.py          # Per-provider 熔断器 (CLOSED/OPEN/HALF_OPEN)
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py                 # 抽象 Provider 接口
│   │   ├── anthropic_compat.py     # Anthropic 兼容直通
│   │   └── openai_compat.py        # Anthropic ↔ OpenAI 协议转换
│   ├── db.py                        # SQLite 调用记录持久化
│   ├── api/
│   │   ├── __init__.py
│   │   └── metrics.py               # /api/metrics, /api/calls 查询接口
│   └── monitoring.py                # 结构化日志
├── dashboard/                        # Vue 前端 (后期完善)
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/
│       ├── App.vue
│       ├── main.ts
│       ├── components/
│       │   ├── StatsCards.vue        # 统计卡片
│       │   ├── CallsTable.vue        # 调用列表
│       │   └── CallDetail.vue        # 单次调用详情
│       └── api/
│           └── index.ts              # API 请求封装
└── tests/
    ├── conftest.py
    ├── test_config.py
    ├── test_routing.py
    ├── test_circuit_breaker.py
    ├── test_providers.py
    └── test_integration.py
```

---

## 依赖

| 依赖 | 用途 |
|---|---|
| `fastapi` | 异步 HTTP 框架，原生 SSE StreamingResponse |
| `uvicorn[standard]` | ASGI 服务器 (uvloop + httptools) |
| `httpx` | 异步 HTTP 客户端，连接池复用，流式支持 |
| `pydantic` | 请求/响应/配置 数据校验 |
| `structlog` | 结构化日志 (请求ID、provider、耗时、结果) |
| `aiosqlite` | 异步 SQLite，调用记录持久化 |
| `orjson` | 高性能 JSON 序列化 |

TOML 解析使用 Python 3.11+ 标准库 `tomllib`，无需额外依赖。

---

## 配置格式 (config.toml)

```toml
[server]
host = "127.0.0.1"
port = 8080

# ==========================================
# Provider 连接设置与实际模型目录
# ==========================================
[providers.anthropic]
type = "anthropic"
api_key = "${ANTHROPIC_API_KEY}"
base_url = "https://api.anthropic.com"

[providers.anthropic.models."claude-haiku-4-5-20251001"]
input_price_per_million = 1.0             # 可选，USD / 1M Token
output_price_per_million = 4.0
cache_read_price_per_million = 0.1
cache_write_price_per_million = 1.25

[providers.anthropic.models."claude-sonnet-4-5-20250929"]

[providers.zhipu]
type = "anthropic"
api_key = "${ZHIPU_API_KEY}"
base_url = "https://api.z.ai/api/anthropic"

[providers.zhipu.models."glm-5.1"]

# ==========================================
# 虚拟模型 — 只保存有序引用与结构化 pin
# ==========================================

[models.haiku-router]
pinned_model = { provider = "anthropic", model = "claude-haiku-4-5-20251001" }
models = [
  { provider = "anthropic", model = "claude-haiku-4-5-20251001" },
  { provider = "zhipu", model = "glm-5.1" },
]

[models.sonnet-router]
pinned_model = { provider = "anthropic", model = "claude-sonnet-4-5-20250929" }
models = [
  { provider = "anthropic", model = "claude-sonnet-4-5-20250929" },
  { provider = "zhipu", model = "glm-5.1" },
]
```

实际模型身份始终是结构化的 `(provider, model)`；`<provider>/<model>` 只用于展示，不用于反向解析。实际模型及四类价格只在 Provider 目录定义一次，虚拟模型数组顺序在运行时生成 `priority = index + 1`。模型费用均可省略：省略值在运行时保持 `None`，写入调用快照时为 SQLite `NULL`，只在计算费用时按 0；显式配置 0 则保留为数值 0。

这是不兼容旧格式的 breaking change。旧版 `[[models.<name>.providers]]`、引用上的 `priority`/价格、字符串 `pinned_model` 与独立 `pinned_provider` 会返回明确错误；系统不自动读取、迁移或改写旧文件。

---

## 核心模块设计

### 1. config.py — 配置加载

**职责：**
- 使用 `tomllib` 加载 TOML 配置文件
- `os.path.expandvars()` 对 `api_key` 等字段做 `${ENV_VAR}` 插值
- Pydantic 校验结构完整性
- 校验 Provider/实际模型引用、重复引用、非负价格和 sticky pin
- 运行时启动允许未解析 `${ENV_VAR}`，用于新环境先打开 dashboard 配置
- 严格校验命令会在环境变量未设置时失败，并打印具体 provider
- 使用结构化 `ConfigError`，可复用解析层不调用 `sys.exit()`

**Pydantic 模型：**

```python
class ActualModelDef(BaseModel):
    input_price_per_million: float | None = None
    output_price_per_million: float | None = None
    cache_read_price_per_million: float | None = None
    cache_write_price_per_million: float | None = None

class ProviderDef(BaseModel):
    type: Literal["anthropic", "openai"]
    api_key: str
    base_url: str
    timeout_seconds: float = 120.0
    models: dict[str, ActualModelDef]

class ModelRef(BaseModel):
    provider: str
    model: str

class VirtualModelDef(BaseModel):
    pinned_model: ModelRef | None
    models: list[ModelRef]

class ProviderConfig(BaseModel):
    # ProviderDef + ActualModelDef + ModelRef + 数组下标的运行时解析结果
    name: str
    model: str
    priority: int
    ...

class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8080

class AppConfig(BaseModel):
    server: ServerConfig
    providers: dict[str, ProviderDef]
    models: dict[str, VirtualModelConfig]
```

**TOML 解析要点：**

解析分为两层：`ConfigDocument` 忠实表达配置文件中的 Provider 目录和 `ModelRef`；`build_runtime_config()` 通过 `(provider, model)` 索引合并 Provider 连接设置、`ActualModelDef` 价格和数组下标，生成 Router 直接消费的完整 `ProviderConfig`。路由层不反查原始配置。

### 1.1 api/config.py — 配置一致性与引用完整性

- `GET /api/config` 返回规范结构并脱敏 API key；Provider 与模型子端点分别返回实际模型目录和有序 `ModelRef`。
- `PUT /api/config` 在接触现有文件前完成候选字段校验、TOML 序列化回读和运行时配置构建。
- 候选准备完成后，通过同目录临时文件原子替换 `config.toml`，再切换 Router 与日志配置。
- 写盘、Router 切换或日志重配置失败时恢复旧文件和旧运行时，并清理临时文件。
- 删除保护比较现有配置与候选配置。仍被引用的 Provider/实际模型返回 `409 {"error": {"code": "provider_in_use" | "model_in_use", "provider": ..., "referenced_by": [...]}}`；模型冲突额外返回 `model`，Provider 冲突省略该字段。用户必须先单独保存引用移除，再执行删除。

### 2. routing.py — 路由引擎

**职责：**
- 接收虚拟模型名 + Anthropic 请求体
- 按 priority 顺序遍历 provider 链
- 每次尝试：调用 provider → 成功则返回 → 失败则判断是否重试
- 全部失败返回 502 + 聚合错误

**错误分类：**

| 错误 | 是否重试 | 熔断 | 说明 |
|---|---|---|---|
| HTTP 401 | ✅ 故障转移 | 🔴 立即熔断 | 认证失败，不会自动恢复 |
| HTTP 403 | ✅ 故障转移 | 🔴 立即熔断 | 权限不足，不会自动恢复 |
| HTTP 429 | ✅ 故障转移 | 🟡 连续触发 | 限流 |
| HTTP 529 | ✅ 故障转移 | 🟡 连续触发 | API 过载 |
| HTTP 5xx | ✅ 故障转移 | 🟡 连续触发 | 服务端错误 |
| `httpx.ConnectError` | ✅ 故障转移 | 🟡 连续触发 | DNS/连接拒绝 |
| `httpx.ConnectTimeout` | ✅ 故障转移 | 🟡 连续触发 | 网络不通 |
| `httpx.ReadTimeout` | ✅ 故障转移 | 🟡 连续触发 | 响应超时 |
| `httpx.RemoteProtocolError` | ✅ 故障转移 | 🟡 连续触发 | 连接异常关闭 |
| HTTP 400, 404, 其他 4xx | ❌ 不重试 | — | 客户端错误，立即返回 |
| 响应非 JSON | ❌ 不重试 | — | 协议错误 |

### 3. circuit_breaker.py — 熔断器

Per-provider 熔断器，防止持续向故障 provider 发送请求。

**状态机：**

```
CLOSED ──(连续失败达阈值)──→ OPEN
  ↑                            │
  │                            └──(recovery_timeout 后)──→ HALF_OPEN
  │                                                            │
  └──(探测成功)────────────────────────────────────────────────┘
HALF_OPEN ──(探测失败)──→ OPEN
```

- **CLOSED**: 正常状态，请求通过
- **OPEN**: 熔断状态，请求被跳过，等待恢复超时
- **HALF_OPEN**: 半开状态，允许一次探测请求

**参数：**
- `failure_threshold` (默认 5): 连续失败次数阈值，达到后熔断
- `recovery_timeout` (默认 600s / 10 分钟): 熔断后等待恢复的时间

**熔断触发策略：**
- 401/403 (认证/权限错误) → 立即熔断（这类错误不会自动恢复）
- 429/529/5xx (限流/过载/服务端错误) → 连续失败达阈值后熔断

**集成方式：** Router 在 `_get_providers()` 中通过 `circuit_breaker.is_available()` 过滤已熔断的 provider，在路由成功/失败时调用 `record_success()`/`record_failure()` 更新状态。

### 4. providers/ — 适配器

#### base.py — 抽象接口

```python
class BaseProvider(ABC):
    def __init__(self, config: ProviderConfig, http_client: httpx.AsyncClient): ...

    @abstractmethod
    async def send(self, request: dict) -> dict:
        """非流式请求，返回完整响应 JSON"""

    @abstractmethod
    async def send_stream(self, request: dict) -> AsyncIterator[bytes]:
        """流式请求，yield SSE 原始字节"""
```

#### anthropic_compat.py — 直通适配器

最简单的适配器：
- 替换请求中的 `model` 为真实模型名
- 设置 `x-api-key` header
- **非流式**: `POST {base_url}/v1/messages` → 返回 JSON
- **流式**: `POST {base_url}/v1/messages` (stream=true) → 直接 yield SSE bytes

适用场景：Anthropic 官方 API、智谱 Anthropic 兼容 API、及其他 Anthropic 格式兼容的 provider。

#### openai_compat.py — 协议转换

Anthropic Messages API 和 OpenAI Chat Completions API 双向转换。

**请求转换 (Anthropic → OpenAI)：**

| Anthropic 字段 | OpenAI 字段 | 转换逻辑 |
|---|---|---|
| `model` | `model` | 替换为真实 OpenAI 模型名 |
| `system` (string/array) | `messages[0]` | 插入 `{"role": "system", "content": ...}` |
| `messages[].role` | `messages[].role` | 直接映射 (user/assistant) |
| `messages[].content` (array) | `messages[].content` (array) | text 块直接映射；image 块转 `image_url` data URL；tool_use 转 `tool_calls`；tool_result 转 `{"role": "tool"}` |
| `tools[]` | `tools[]` | `{"name":..., "input_schema":...}` → `{"type":"function","function":{"name":...,"parameters":...}}` |
| `tool_choice` | `tool_choice` | 格式映射 |
| `max_tokens` | `max_tokens` | 直接映射 |
| `temperature` | `temperature` | 直接映射 |
| `stream` | `stream` | 直接映射 |

**响应转换 (OpenAI → Anthropic)：**

| OpenAI 字段 | Anthropic 字段 | 转换逻辑 |
|---|---|---|
| `choices[0].message.content` | `content[]` | 字符串 → `[{"type":"text","text":"..."}]` |
| `choices[0].message.tool_calls[]` | `content[]` | 每个 tool_call → `{"type":"tool_use","id":...,"name":...,"input":...}` |
| `choices[0].finish_reason` | `stop_reason` | `"stop"`→`"end_turn"`, `"tool_calls"`→`"tool_use"`, `"length"`→`"max_tokens"` |
| `model` | `model` | 替换回虚拟模型名 |
| `usage` | `usage` | 直接映射 input/output tokens |

**流式 SSE 转换：**

OpenAI 流式格式：
```
data: {"object":"chat.completion.chunk","choices":[{"delta":{"role":"assistant"},"index":0}]}
data: {"object":"chat.completion.chunk","choices":[{"delta":{"content":"Hello"},"index":0}]}
data: {"object":"chat.completion.chunk","choices":[{"finish_reason":"stop"},"index":0}]}
data: [DONE]
```

Anthropic 流式格式：
```
event: message_start
data: {"type":"message_start","message":{"id":"...","model":"...","content":[],"role":"assistant",...}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{...}}

event: message_stop
data: {"type":"message_stop"}
```

这是整个项目最复杂的部分，先实现非流式，流式转换作为后续增强。

### 5. app.py — FastAPI 应用

**端点：**

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/health` | 健康检查，返回 `{"status":"ok"}` |
| `GET` | `/v1/models` | 返回虚拟模型列表，Anthropic List Models 格式 |
| `POST` | `/v1/messages` | 主聊天端点 |
| `POST` | `/v1/messages?beta=true` | Claude Code 可能带 beta 参数，忽略即可 |

**`POST /v1/messages` 处理流程：**

1. 读取请求体 JSON
2. 提取 `model` 字段 → 查找虚拟模型对应的 provider 链
3. 未找到 → 返回 400 + 已知模型列表
4. `stream: true` → `StreamingResponse(routing.send_stream(...), media_type="text/event-stream")`
5. `stream: false` → `JSONResponse(routing.send(...))`

**`GET /v1/models` 响应格式：**

```json
{
  "data": [
    {"id": "haiku-router", "type": "model", "display_name": "haiku-router", "created_at": "2025-01-01T00:00:00Z"},
    {"id": "sonnet-router", "type": "model", "display_name": "sonnet-router", "created_at": "2025-01-01T00:00:00Z"}
  ]
}
```

### 6. main.py — 入口

```python
def main():
    parser = argparse.ArgumentParser(description="Agent Router - LLM API 路由代理")
    parser.add_argument("--config", "-c", default="config.toml", help="配置文件路径")
    parser.add_argument("--host", default=None, help="覆盖 server.host")
    parser.add_argument("--port", "-p", type=int, default=None, help="覆盖 server.port")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.host: config.server.host = args.host
    if args.port: config.server.port = args.port

    app = create_app(config)
    uvicorn.run(app, host=config.server.host, port=config.server.port)
```

### 7. db.py — 调用记录持久化

使用 `aiosqlite` 异步写入 SQLite，记录每次 API 调用的完整信息。

**表结构：**

```sql
CREATE TABLE IF NOT EXISTS calls (
    id              TEXT PRIMARY KEY,        -- UUID, 请求唯一标识
    timestamp       TEXT NOT NULL,           -- ISO 8601 时间戳
    virtual_model   TEXT NOT NULL,           -- 虚拟模型名 (如 "haiku-router")
    provider_name   TEXT,                    -- Provider 配置名 (如 "anthropic")
    provider_type   TEXT,                    -- 最终成功的 provider 类型 (anthropic/openai)
    provider_model  TEXT,                    -- 真实模型名 (如 "claude-haiku-4-5")
    provider_url    TEXT,                    -- 实际调用的 API 端点
    attempt         INTEGER DEFAULT 1,       -- 第几次尝试成功
    latency_ms      INTEGER,                 -- 总耗时 (毫秒)

    -- 请求信息
    request_body    TEXT,                    -- 完整请求体 JSON
    request_tokens  INTEGER,                 -- 输入 token 估算 (消息长度)

    -- 响应信息
    status          TEXT NOT NULL,           -- success / error
    error_type      TEXT,                    -- 错误类型 (rate_limit, server_error, timeout, etc.)
    error_message   TEXT,                    -- 错误详情
    response_body   TEXT,                    -- 完整响应体 JSON (非流式) 或截断版

    -- Token 用量 (从响应中提取)
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cache_read_tokens   INTEGER,            -- Anthropic cache 读取
    cache_write_tokens  INTEGER,            -- Anthropic cache 写入

    -- 最终成功模型的价格快照 (USD / 1M Token；未配置为 NULL)
    input_price_per_million        REAL,
    output_price_per_million       REAL,
    cache_read_price_per_million   REAL,
    cache_write_price_per_million  REAL,

    -- 按上述快照与 Token 用量计算的最终费用
    cost_usd        REAL,
    failover_details TEXT                  -- 失败尝试链 JSON
);

CREATE INDEX IF NOT EXISTS idx_calls_timestamp ON calls(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_calls_model ON calls(virtual_model);
CREATE INDEX IF NOT EXISTS idx_calls_status ON calls(status);
```

**写入语义：**

- 非流式与流式请求都在最终 Provider 成功后写入其结构化 `provider_name`、`provider_model` 和四类价格快照；首选失败后的 failover 使用最终成功模型的数据。
- `cost_usd = Σ(token_count × (price_snapshot or 0)) / 1_000_000`。未配置价格的快照保持 `NULL`，只在公式中按 0；显式价格 0 保持为 0。
- 没有实际成功模型的失败调用不写入价格，四类字段保持 `NULL`。
- 价格是调用发生时的快照；修改当前配置只影响后续调用，不回写历史记录。

**Schema 兼容性：** 当前版本不兼容缺少价格快照字段的旧数据库，也不提供增量迁移。`CallStore` 在执行任何 DDL 前通过只读连接检查现有 `calls` 表；不兼容时列出缺失字段并要求开发者备份后手动重命名或删除旧库。检测失败不会修改或覆盖原文件。

### 8. api/metrics.py — 数据查询 API

为 dashboard 提供数据查询接口：

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/metrics/summary` | 概览统计 (总调用数、成功率、总 token、总费用) |
| `GET` | `/api/metrics/by-model` | 按虚拟模型分组统计 |
| `GET` | `/api/metrics/by-real-model` | 按 `(provider_name, provider_model)` 复合分组，返回独立 `provider`、`model` 字段 |
| `GET` | `/api/metrics/by-provider` | 按 provider 分组统计 |
| `GET` | `/api/calls?page=1&size=50` | 分页查询调用列表，可按独立 `provider`、`provider_model` 字段筛选 |
| `GET` | `/api/calls/{id}` | 单次调用详情 (含完整 request/response) |
| `GET` | `/api/metrics/daily` | 每日调用、四类 Token 与折算成本趋势 |

### 9. monitoring.py — 日志

使用 `structlog` 记录结构化日志，覆盖请求全生命周期：

```
# 请求级别
{"event": "request.start", "request_id": "abc123", "model": "haiku-router", "stream": true, "timestamp": "..."}
{"event": "request.end", "request_id": "abc123", "status": "success", "latency_ms": 1234, "attempt": 1}

# Provider 级别
{"event": "provider.try", "request_id": "abc123", "provider": "anthropic", "model": "claude-haiku-4-5", "priority": 1}
{"event": "provider.fail", "request_id": "abc123", "provider": "anthropic", "error": "HTTP 429", "retry": true, "latency_ms": 50}
{"event": "provider.try", "request_id": "abc123", "provider": "anthropic", "model": "glm-5.1", "priority": 2}
{"event": "provider.success", "request_id": "abc123", "provider": "anthropic", "status_code": 200, "latency_ms": 1200}

# Token 用量
{"event": "token.usage", "request_id": "abc123", "input": 1500, "output": 300, "cache_read": 0, "cache_write": 0, "cost_usd": 0.015}

# 故障转移
{"event": "failover", "request_id": "abc123", "from": "anthropic:claude-haiku-4-5", "to": "anthropic:glm-5.1", "reason": "rate_limit"}
{"event": "failover.exhausted", "request_id": "abc123", "attempts": 3, "errors": [...]}

# 系统级别
{"event": "server.start", "host": "127.0.0.1", "port": 8080}
{"event": "server.shutdown", "reason": "SIGTERM", "pending_requests": 0}
```

每条日志带 `request_id` 方便串联排查。

### 10. Dashboard (Vue) — 后期完善

Vue 3 + Vite + TypeScript 前端，从 router 的 `/api/*` 接口获取数据。

**页面布局：**
```
┌─────────────────────────────────────────────────────┐
│  Agent Router Dashboard                   [刷新]    │
├──────────┬──────────┬──────────┬────────────────────┤
│ 总调用数  │ 成功率    │ 总 Token  │  总费用 (USD)      │
│  1,234   │  98.5%   │  2.3M    │  $45.20           │
├──────────┴──────────┴──────────┴────────────────────┤
│  调用趋势 (折线图)                                    │
│  ▁▂▄▆▇▇▆▅▃▂▁▂▃▅▆▇▇▆▅▄▃▂▁▂▃▄▅▆▇                    │
├─────────────────────────────────────────────────────┤
│  真实模型分布与统计                                      │
│  anthropic/claude-haiku 60% · zai/glm-5.1 40%         │
├─────────────────────────────────────────────────────┤
│  最近调用列表                                        │
│  时间 │ 模型 │ Provider │ 状态 │ 延迟 │ Token │ 费用  │
│  ...  │ ...  │ ...      │ ✅   │ 1.2s │ 1500  │ $0.01 │
│  ...  │ ...  │ ...      │ ❌   │ 50ms │ 0     │ $0.00 │
└─────────────────────────────────────────────────────┘
```

**技术栈：** Vue 3 + TypeScript + Vite + ECharts (图表) + Tailwind CSS

dashboard 作为独立 Vue 目录构建，由独立面板服务代理 router 的 `/api/*` 与 `/v1/*` 请求。

真实模型图表、统计表、Calls 筛选项和调用详情统一通过 `formatActualModel(provider, model)` 生成 `<provider>/<model>`。Provider 与模型在 API、store 和筛选查询中始终是独立字段，展示字符串不参与身份解析。调用详情额外展示四类价格快照，以区分未配置 (`NULL`) 与显式 0。

配置页的数据层与后端领域模型一致：Provider draft 持有 `models: Record<string, ActualModelConfig>`，虚拟模型 draft 只持有有序 `models: ModelRef[]` 和 `pinned_model: ModelRef | null`。虚拟模型页通过按 Provider 分组的组合选择器引用已有实际模型，禁止自由输入、重复引用和引用不存在的目录项；拖拽只改变数组顺序。Provider 或实际模型仍被引用时，前端消费后端固定的 `provider_in_use` / `model_in_use` 错误和 `referenced_by` 列表，保留当前数据并提示先移除引用。

---

## Claude Code 配置方式

修改 `.claude/settings.json`：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:8080",
    "ANTHROPIC_AUTH_TOKEN": "dummy",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "haiku-router",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "sonnet-router",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "opus-router"
  }
}
```

`ANTHROPIC_AUTH_TOKEN` 填任意值即可（router 不校验，真实 API key 在 config.toml 中配置）。`ANTHROPIC_BASE_URL` 指向本地 router。

---

## 关键设计决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 配置格式 | TOML | Python 标准库支持，项目统一 (pyproject.toml)，可读性好 |
| 路由状态 | 有状态 (熔断器) | 每请求独立遍历 provider 链，但通过熔断器跳过持续故障的 provider |
| 流式故障转移 | 无缓冲直传 | SSE 字节边收边发，优先保证延迟；流中断由 Claude Code 自动重试触发下一 provider |
| HTTP 客户端 | 单实例复用 | 进程级 httpx.AsyncClient，按 base_url 自动连接池隔离 |
| 配置热更新 | 原子写盘 + 运行时回滚 | 候选配置先完整验证；文件、Router、日志任一步失败都恢复旧状态 |
| Provider 接口 | 统一 Anthropic 格式 | routing.py 不感知后端协议，OpenAI 适配器内部转换 |
| 熔断策略 | Per-provider 三态 | 401/403 立即熔断，429/529/5xx 连续失败后熔断，60s 后半开探测 |

---

## 错误处理全景

| 场景 | 行为 |
|---|---|
| 虚拟模型未配置 | 400 + 已知模型列表 |
| 所有 provider 失败 | 502 + 聚合错误详情 |
| 所有 provider 熔断 | 502 (无可用 provider) |
| provider 返回 401/403 | 故障转移 + 立即熔断该 provider |
| provider 连续返回 429/529/5xx | 故障转移 + 达阈值后熔断 |
| 熔断 provider 恢复 | 60s 后半开探测，成功则关闭熔断器 |
| 环境变量未设置 | `serve` 可启动；路由时跳过对应 provider；`config validate` 严格失败 |
| provider 返回非 JSON | 不可重试，立即返回 502 |
| 流传输中断 | 关闭客户端连接，日志记录 |
| 客户端断开 | 取消上游请求 (asyncio.CancelledError) |
| 请求体过大 (>50MB) | 413 |
| SIGTERM | 优雅关闭：停止接收新请求，等待进行中请求完成 (30s 超时) |

---

## 实现顺序

| 阶段 | 内容 | 测试 |
|---|---|---|
| 1 | pyproject.toml 依赖 + 目录结构 | - |
| 2 | config.py (TOML 加载 + Pydantic 校验) | 合法/非法配置、环境变量插值、缺失变量报错 |
| 3 | providers/base.py + providers/anthropic_compat.py | mock 上游，验证直通和 header 替换 |
| 4 | routing.py (优先级链 + 故障转移) | 成功/429/5xx/超时/全部失败 各场景 |
| 5 | app.py + main.py (FastAPI + 入口) | /health /v1/models /v1/messages |
| 6 | monitoring.py (结构化日志) | 日志级别、request_id 串联 |
| 7 | db.py (SQLite 调用记录) + api/metrics.py | 写入/查询调用记录 |
| 8 | config.toml (示例配置) | - |
| 9 | providers/openai_compat.py (协议转换，先非流式) | 请求/响应转换正确性 |
| 10 | dashboard/ (Vue 骨架) | 页面渲染、API 数据加载 |
| 11 | 集成测试 + 端到端验证 | 启动 router → curl 测试 → Claude Code 配置测试 |

---

## 验证方式

```bash
# 1. 启动
uv run agent-router --config config.toml

# 2. 健康检查
curl http://127.0.0.1:8080/health

# 3. 模型列表
curl http://127.0.0.1:8080/v1/models

# 4. 非流式请求
curl -s -X POST http://127.0.0.1:8080/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model":"haiku-router","max_tokens":100,"messages":[{"role":"user","content":"你好"}]}'

# 5. 流式请求
curl -s -X POST http://127.0.0.1:8080/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model":"haiku-router","max_tokens":100,"stream":true,"messages":[{"role":"user","content":"你好"}]}'

# 6. 故障转移测试 (故意配错第一个 provider 的 base_url)
```
