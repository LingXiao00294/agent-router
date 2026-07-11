# Agent Router

本地 LLM API 路由代理，将虚拟模型名映射到多个 provider，按优先级进行故障转移。

```
Claude Code → router (本地 FastAPI) → 智谱 API      (优先级 1)
                                    → 火山引擎      (优先级 2, 故障转移)
                                    → DeepSeek      (优先级 3, 故障转移)
```

## 快速开始

```bash
# 1. 安装依赖
uv sync

# 2. 可选：配置环境变量
cp .env.example .env   # 可先跳过，之后也可通过 dashboard 填写 API key

# 3. 创建路由配置
cp config.toml.example config.toml   # 可直接启动，之后通过 dashboard 添加 provider

# 4. 启动 router
uv run agent-router serve

# 5. 单独启动 dashboard（另一个终端）
uv run agent-router dashboard

# 6. 验证 router
curl http://127.0.0.1:9456/health
```

router 默认监听 `http://127.0.0.1:9456`，dashboard 默认监听 `http://127.0.0.1:5173` 并代理到 router。

也可以先构建 dashboard，再安装成用户级工具：

```bash
cd dashboard
bun install
bun run build
cd ..

uv tool install .
agent-router serve
agent-router-dashboard
```

## CLI

CLI 基于 Typer 实现。`agent-router` 默认等价于 `agent-router serve`，旧启动方式仍然可用。Dashboard 已从 router 中拆出，可以用 `agent-router dashboard` 子命令或独立的 `agent-router-dashboard` 命令启动。

```bash
uv run agent-router --help

# 启动 router
uv run agent-router
uv run agent-router serve -c config.toml --db calls.db --host 127.0.0.1 --port 9456

# 启动 dashboard
uv run agent-router dashboard --router-url http://127.0.0.1:9456
uv run agent-router-dashboard --router-url http://127.0.0.1:9456

# 配置管理
uv run agent-router config init
uv run agent-router config validate -c config.toml
uv run agent-router config show -c config.toml --format json

# 路由排查
uv run agent-router providers -c config.toml
uv run agent-router models -c config.toml
uv run agent-router doctor -c config.toml --db calls.db

# 调用记录
uv run agent-router stats --db calls.db
uv run agent-router calls list --db calls.db --limit 20 --status error
uv run agent-router calls show <call-id> --db calls.db --format json
```

`config init` 默认从 `config.toml.example` 生成 `config.toml`，目标文件已存在时不会覆盖；确需覆盖时添加 `--force`。`config validate`、`doctor` 和 `serve` 默认加载 `.env`，可用 `--no-env-file` 跳过。`serve` 允许 `api_key = "${ENV_VAR}"` 暂未解析，以便新环境先启动后端和 dashboard；实际路由时这类 provider 会被跳过。`config validate` 仍按严格模式检查，适合在正式使用前确认环境变量和配置完整。`dashboard` 默认查找安装包内或源码目录下已构建的 `dashboard/dist`；找不到时需要先执行 `cd dashboard && bun install && bun run build` 后重新安装，或通过 `--dist` 指向构建目录。

### 配合 Claude Code 使用

修改 `~/.claude/settings.json`，添加以下配置将 Claude Code 的 API 请求指向本地路由代理：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:9456",
    "ANTHROPIC_AUTH_TOKEN": "dummy",
    "ANTHROPIC_MODEL": "opus-router",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "opus-router",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "sonnet-router",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "haiku-router",
    "CLAUDE_CODE_SUBAGENT_MODEL": "opus-router",
  }
}
```

> **注意**：`ANTHROPIC_AUTH_TOKEN` 可以设为任意非空值（如 `dummy`），router 不会校验 token。三个 `DEFAULT_*_MODEL` 需与 `config.toml` 中定义的虚拟模型名一致。

## 配置

### config.toml

```toml
[server]
host = "127.0.0.1"
port = 9456
log_level = "debug"

# Provider 定义 — 每个 provider 只配置一次
[providers.zai]
type = "anthropic"
api_key = "${ZAI_API_KEY}"
base_url = "https://api.z.ai/api/anthropic"

[providers.deepseek]
type = "anthropic"
api_key = "${DEEPSEEK_API_KEY}"
base_url = "https://api.deepseek.com/anthropic"

# 虚拟模型 — 引用 provider + 真实模型名 + 优先级 (越小越优先)
[[models.opus-router]]
provider = "zai"
model = "glm-5.1"
priority = 1

[[models.opus-router]]
provider = "deepseek"
model = "deepseek-v4-pro"
priority = 2
```

`${ENV_VAR}` 会自动从环境变量或 `.env` 文件展开。未设置时不会阻止 `serve` 启动，方便先打开 dashboard 修改配置；包含未解析 key 的 provider 在实际请求路由时会被跳过，全部 provider 都不可用时返回明确错误。支持 `type = "anthropic"`（Anthropic Messages API 兼容 provider）。

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `GET` | `/v1/models` | 列出虚拟模型（Anthropic 格式） |
| `POST` | `/v1/messages` | 聊天接口，支持 `stream: true/false` |
| `GET` | `/api/metrics/summary` | 调用概览统计 |
| `GET` | `/api/metrics/by-model` | 按虚拟模型分组统计 |
| `GET` | `/api/metrics/by-provider` | 按 provider 分组统计 |
| `GET` | `/api/metrics/by-real-model` | 按真实模型分组统计 |
| `GET` | `/api/metrics/daily?days=30` | 每日调用趋势 |
| `GET` | `/api/calls?page=1&size=50` | 分页查询调用记录 |
| `GET` | `/api/calls/{id}` | 单次调用详情 |
| `GET` | `/api/config` | 查看配置（api_key 脱敏） |
| `PUT` | `/api/config` | 更新配置 |

## Dashboard

```bash
cd dashboard
bun install
bun run dev       # 前端开发模式 (Vite 代理到 127.0.0.1:9456)
bun run build     # 生产构建 → dashboard/dist/
```

构建后通过 `uv run agent-router dashboard` 启动独立面板，访问 `http://127.0.0.1:5173`。
为防止误清空上游，Dashboard 保存配置时要求至少保留一个 provider 和一个虚拟模型；该限制不改变配置 API 或 TOML 格式。
虚拟模型的 provider 引用可通过左侧拖拽把手排序，列表顺序即 failover 使用的 `priority` 顺序。
Dashboard 顶栏以“故障转移”开关呈现路由模式：关闭时为指定模型模式（内部仍使用 `sticky`），开启时按优先级自动故障转移。路由默认使用指定模型模式；模型未设置有效 pin 时会默认选择第一优先级的有效模型引用。切换到指定模型模式前，每个虚拟模型都必须存在有效 pin，否则切换会失败并返回具体模型名称，原配置保持不变。

## 开发

```bash
uv run pytest                          # 运行测试
uv run pytest tests/test_routing.py -v # 单个测试文件
uv run ruff check src tests            # Lint
uv run ty check src tests              # 类型检查
```

## 项目结构

```
src/agent_router/
├── main.py              # console_scripts 薄入口
├── cli.py               # CLI 子命令：serve/dashboard/config/models/providers/calls/stats/doctor
├── dashboard.py         # 独立 dashboard 静态服务 + API 代理
├── app.py               # FastAPI 应用 + 路由处理
├── config.py            # TOML 加载 + ${ENV_VAR} 展开 + Pydantic 校验
├── routing.py           # 核心：优先级链 + 故障转移
├── db.py                # SQLite 调用记录 (aiosqlite)
├── monitoring.py        # 结构化日志 (structlog)
├── providers/
│   ├── base.py          # 抽象 Provider 接口
│   └── anthropic_compat.py  # Anthropic 兼容直通适配器
└── api/
    ├── metrics.py       # /api/metrics, /api/calls 查询接口
    └── config.py        # /api/config 配置读写接口

dashboard/               # Vue 3 + Vite + ECharts 监控面板
tests/                   # pytest (asyncio_mode=auto)
docs/design.md           # 详细设计文档
```

## 故障转移

路由引擎按 priority 升序遍历 provider，成功即返回。错误分类：

- **可重试**（自动切换下一个 provider）：HTTP 429、529、5xx、连接/超时错误
- **立即熔断**（故障转移 + 熔断该 provider）：HTTP 401、403（认证/权限错误，不会自动恢复）
- **连续熔断**（连续达阈值后熔断）：HTTP 429、529、5xx（默认 5 次连续失败）
- **不可重试**（立即返回错误）：HTTP 4xx（除 401/403/429）、协议错误、响应非 JSON
- **全部失败**：返回 502 + 聚合错误信息

熔断的 provider 在恢复超时（默认 60s）后进入半开状态，允许一次探测请求：成功则关闭熔断器，失败则重新熔断。
