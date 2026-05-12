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
uv run agent-router                    # 启动 (默认读取 config.toml)
uv run agent-router -c config.toml -p 9456 --db calls.db
uv run pytest                          # 运行所有测试
uv run pytest tests/test_routing.py -v # 运行单个测试文件
uv run ruff check src tests            # Lint
uv run ty src tests                    # 类型检查

# 前端 Dashboard
cd dashboard && npm run dev            # 开发模式 (Vite 代理后端到 127.0.0.1:9456)
cd dashboard && npm run build          # 生产构建 → dashboard/dist/
```

## 架构

### 配置层 (`config.py`)

- `config.toml` 定义 `[server]`、`[providers.*]`、`[[models.*]]`
- `${ENV_VAR}` 在加载时通过 `os.path.expandvars` 展开
- 虚拟模型 → 按 priority 排序的 `list[ProviderConfig]`
- `[[models.*]]` 支持可选的费用字段: `cost_input`、`cost_output`、`cost_cache_read`、`cost_cache_write`（单位: $/M tokens）
- `.env` 和 `config.toml` 已在 `.gitignore` 中，不会提交

### 路由层 (`routing.py`)

- `Router` 接收虚拟模型名，按优先级遍历 provider 列表
- 成功时返回第一个 provider 的响应，失败时尝试下一个（可重试错误）或立即失败（不可重试错误）
- 支持流式（`route_stream` → `AsyncIterator[bytes]`）和非流式（`route_non_stream` → `dict`）
- `RetryableError`: 429、529、5xx、连接/超时错误 → 故障转移
- `RetryableError(immediate_break=True)`: 401、403 → 故障转移 + 立即熔断该 provider
- `NonRetryableError`: 4xx（不含 401/403/429）、协议错误 → 立即失败
- 熔断器过滤已熔断的 provider，不再对其发起新请求

### 熔断器 (`circuit_breaker.py`)

- Per-provider 熔断器，三态：`CLOSED` → `OPEN` → `HALF_OPEN` → `CLOSED`
- 401/403（认证失败）→ 立即熔断（`immediate_break=True`），不会自动恢复
- 429/529/5xx 连续失败达阈值（默认 5 次）→ 熔断
- 熔断后等待恢复超时（默认 60s）→ 进入半开状态，允许一次探测请求
- 探测成功 → 关闭熔断器；探测失败 → 重新熔断

### Provider 层 (`providers/`)

- `BaseProvider`: 抽象基类，定义 `send()` 和 `send_stream()` 接口
- `AnthropicCompatProvider`: Anthropic Messages API 兼容直通适配器，适用于 Anthropic 官方及兼容 API（智谱 GLM、DeepSeek 等）
- 通过 `_create_provider()` 工厂函数根据 `config.type` 创建实例

### App 层 (`app.py`)

- FastAPI 应用，lifespan 中初始化 CallStore 和 httpx 客户端
- 流式响应包装器 `_stream_wrapper` 从 SSE 流中正则提取 usage token 信息后写入数据库
- `_calculate_cost`: 根据 token 用量和模型费率配置自动计算 `cost_usd`
- Dashboard 静态文件挂载在 `/assets`，SPA fallback 路由放在最后
- 错误处理: UnknownModelError → 400，AllProvidersFailedError → 502

### 数据层 (`db.py`)

- aiosqlite 单文件数据库 `calls.db`
- `CallStore` 提供 `record()`、`list_calls()`、`summary()`、`by_model()`、`by_provider()`、`daily_trend()` 等方法
- 统计查询包含 cache token 字段: `cache_read_tokens`、`cache_write_tokens`
- `_estimate_request_tokens`: 通过字符数粗略估算请求 token 数

### 监控 (`monitoring.py`)

- structlog 结构化日志，debug 级别使用彩色 ConsoleRenderer，info 及以上使用 JSONRenderer

### API 路由

- `/health` — 健康检查
- `/v1/messages` — Messages API（流式/非流式）
- `/v1/models` — 列出虚拟模型
- `/api/metrics/*` — 调用统计 API（summary、by-model、daily 等）
- `/api/config` — 配置读写 API（api_key 脱敏处理）

### Dashboard

- Vue 3 + Vite + TypeScript + ECharts + Vue Router
- 页面: Dashboard（统计卡片含 cache 统计、模型图表含 4 层 token 堆叠、调用表格、趋势图）、Config（配置管理含模型费用配置）
- 开发时 Vite dev server 将 `/api`、`/health`、`/v1` 代理到后端

## 测试

- `conftest.py`: 提供 `sample_config`（虚拟模型 → mock provider，provider 含 `name` 字段）和 `http_client` fixture
- `pytest.ini_options`: `asyncio_mode = "auto"`，所有测试自动支持 async
- 使用 `pytest-httpx` 模拟 HTTP 响应
- `test_circuit_breaker.py`: 熔断器单元测试 + Router 集成测试
