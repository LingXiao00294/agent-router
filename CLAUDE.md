# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

agent-router 是一个本地 LLM API 路由代理，将虚拟模型名映射到多个 provider，按优先级进行故障转移。暴露 Anthropic Messages API 兼容的 `/v1/messages` 端点，同时提供 Vue 监控面板。

## 工作流

- **所有代码改动必须在 master 之外的分支上进行**，禁止直接在 master 上编辑或提交。
- **分支命名**遵循 `<type>/<description>` 格式（如 `feat/`、`fix/`、`chore/`、`docs/`），description 使用短横线连接的小写英文。

## 常用命令

```bash
# Python 后端
uv sync                                    # 安装/同步依赖（Python >=3.12）
uv run agent-router                        # 启动 (默认读取 config.toml)
uv run agent-router -c config.toml -p 9089 --db calls.db
uv run pytest                              # 运行所有测试
uv run pytest tests/test_routing.py -v     # 运行单个测试文件
uv run pytest -k "test_name" -v            # 按名称匹配运行
uv run ruff check src tests                # Lint
uv run ty check src tests                 # 类型检查

# 前端 Dashboard
cd dashboard && npm run dev                # 开发模式 (Vite 代理后端到 127.0.0.1:9089)
cd dashboard && npm run build              # 生产构建 → dashboard/dist/
```

## 架构

### 配置层 (`config.py`)

- `config.toml` 定义 `[server]`、`[router]`、`[providers.*]`、`[[models.*]]`
- `${ENV_VAR}` 在加载时通过 `os.path.expandvars` 展开
- 虚拟模型 → 按 priority 排序的 `list[ProviderConfig]`
- `[router]` 段配置全局默认 `failure_threshold`（默认 5）和 `recovery_timeout`（默认 600s）
- 每个 provider 可单独设置 `failure_threshold`/`recovery_timeout`/`timeout_seconds`（在 `[providers.*]` 段），**覆盖**全局默认值；路由时实际生效的是 provider 级别的值（见 `routing.py` 中 `provider_cfg.failure_threshold`）
- provider `name` 字段来自 TOML 中的 `[providers.<name>]` 键，无需显式填写
- `load_config` 校验失败时调用 `sys.exit(1)`；热重载时 app 层捕获 `SystemExit` 转为 `RuntimeError`，保留旧配置不变
- `.env` 和 `config.toml` 已在 `.gitignore` 中，不会提交

### 路由层 (`routing.py`)

- `Router` 接收虚拟模型名，按优先级遍历 provider 列表
- 成功时返回第一个 provider 的响应，失败时尝试下一个（可重试错误）或立即失败（不可重试错误）
- 支持流式（`route_stream` → `AsyncIterator[bytes]`）和非流式（`route_non_stream` → `dict`）
- `RetryableError`: 429、529、5xx、连接/超时错误 → 故障转移
- `RetryableError(immediate_break=True)`: 401、403 → 故障转移 + 立即熔断该 provider
- `NonRetryableError`: 4xx（不含 401/403/429）、协议错误 → 立即失败
- **SSE 流内错误检测**（`_check_stream_error`）：部分 provider 返回 HTTP 200 但在 SSE 流体中夹带 `event: error`（如限流）；路由层扫描流缓冲区，按 error type 分类为可重试/立即熔断/不可重试。非已知类型的流错误默认按**不可重试**处理（不盲目故障转移）
- 熔断器过滤已熔断的 provider，不再对其发起新请求；若所有 provider 均已熔断，直接抛 `AllProvidersFailedError`
- `outcome` 字典贯穿路由方法，用于捕获实际命中的 provider 信息和故障转移明细，供 app 层写入数据库
- `reload_config` 热重载保留 http_client 和熔断器状态

### 熔断器 (`circuit_breaker.py`)

- Per-provider 熔断器，三态：`CLOSED` → `OPEN` → `HALF_OPEN` → `CLOSED`
- 401/403（认证失败）→ 立即熔断（`immediate_break=True`），不会自动恢复
- 429/529/5xx 连续失败达阈值（默认 5 次，可通过 `[router].failure_threshold` 配置）→ 熔断
- 熔断后等待恢复超时（默认 600s，可通过 `[router].recovery_timeout` 配置）→ 进入半开状态，允许一次探测请求
- 探测成功 → 关闭熔断器；探测失败 → 重新熔断

### Provider 层 (`providers/`)

- `BaseProvider`: 抽象基类，定义 `send()` 和 `send_stream()` 接口
- `AnthropicCompatProvider`: Anthropic Messages API 兼容直通适配器，适用于 Anthropic 官方及兼容 API（智谱 GLM、DeepSeek 等）
- 通过 `_create_provider()` 工厂函数根据 `config.type` 创建实例

### App 层 (`app.py`)

- FastAPI 应用，lifespan 中初始化 CallStore 和 httpx 客户端
- 流式响应包装器 `_stream_wrapper` 从 SSE 流中正则提取 usage token 信息后写入数据库
- Dashboard 静态文件挂载在 `/assets`，SPA fallback 路由放在最后
- 错误处理: UnknownModelError → 400，AllProvidersFailedError → 502

### 数据层 (`db.py`)

- aiosqlite 单文件数据库 `calls.db`
- `CallStore` 提供 `record()`、`list_calls()`、`summary()`、`by_model()`、`by_provider()`、`daily_trend()` 等方法
- `_estimate_request_tokens`: 通过字符数粗略估算请求 token 数

### 监控 (`monitoring.py`)

- structlog 结构化日志，经 `ProcessorFormatter` 统一桥接 structlog / stdlib / uvicorn 日志到同一渲染管线
- debug 级别彩色 ConsoleRenderer（开发），info 及以上 JSONRenderer（生产），输出到 stdout，时间戳 UTC ISO
- 敏感字段（api_key / authorization / token 等）经 `redact_secrets` processor 自动脱敏
- `request_id` 由 HTTP 中间件注入 contextvars，routing / circuit / app 全链路自动贯穿；支持 `X-Request-ID` 请求头透传与响应头回写
- `log_level` 支持 `PUT /api/config` 热重载（`reconfigure_logging`）
- uvicorn 文本 access log 已关闭，由中间件的结构化 `http.request` 日志接管

### API 路由

- `/health` — 健康检查
- `/v1/messages` — Messages API（流式/非流式）
- `/v1/models` — 列出虚拟模型（Anthropic List Models 格式）
- `/api/metrics/*` — 调用统计 API（summary、by-model、by-real-model、by-provider、daily）
- `/api/calls`、`/api/calls/{id}` — 分页调用记录与详情
- `/api/config`、`/api/config/providers`、`/api/config/models` — 配置读写（PUT 触发热重载，api_key 脱敏）
- `/api/circuit-breaker` — 查询所有 provider 熔断状态
- `/api/circuit-breaker/{provider}/reset` — 手动重置指定 provider 的熔断器

### Dashboard

- Vue 3 + Vite + TypeScript + ECharts + Vue Router
- 页面: Dashboard（统计卡片、模型图表、调用表格、趋势图）、Config（配置管理）
- 开发时 Vite dev server 将 `/api`、`/health`、`/v1` 代理到后端

## 测试

- `conftest.py`: 提供 `sample_config`（虚拟模型 → mock provider，provider 含 `name` 字段）和 `http_client` fixture
- `pytest.ini_options`: `asyncio_mode = "auto"`，所有测试自动支持 async
- 使用 `pytest-httpx` 模拟 HTTP 响应
- 测试文件：`test_routing.py`（路由核心）、`test_circuit_breaker.py`（熔断器 + Router 集成）、`test_config.py`（配置加载/热重载）、`test_providers.py`（provider 适配器）、`test_integration.py`（端到端集成）
