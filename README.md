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

# 2. 配置环境变量
cp .env.example .env   # 编辑 .env，填入各 provider 的 API key

# 3. 创建路由配置
cp config.toml.example config.toml   # 编辑 config.toml，定义 provider 和虚拟模型映射

# 4. 启动
uv run agent-router

# 5. 验证
curl http://127.0.0.1:9456/health
```

启动后可访问 `http://127.0.0.1:9456` 打开监控面板。

### 配合 Claude Code 使用

修改 `~/.claude/settings.json`，添加以下配置将 Claude Code 的 API 请求指向本地路由代理：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:9456",
    "ANTHROPIC_AUTH_TOKEN": "dummy",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "opus-router",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "sonnet-router",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "haiku-router"
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

`${ENV_VAR}` 会自动从环境变量或 `.env` 文件展开。支持 `type = "anthropic"`（Anthropic Messages API 兼容 provider）。

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
npm install
npm run dev       # 开发模式 (Vite 代理到 127.0.0.1:9456)
npm run build     # 生产构建 → dashboard/dist/
```

构建后启动 router，访问 `http://127.0.0.1:9456` 即可使用面板。

## 开发

```bash
uv run pytest                          # 运行测试
uv run pytest tests/test_routing.py -v # 单个测试文件
uv run ruff check src tests            # Lint
uv run ty src tests                    # 类型检查
```

## 项目结构

```
src/agent_router/
├── main.py              # 入口：argparse + uvicorn
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

- **可重试**（自动切换下一个 provider）：HTTP 401、403、429、5xx、连接/超时错误
- **不可重试**（立即返回错误）：HTTP 4xx（除 401/403/429）、协议错误、响应非 JSON
- **全部失败**：返回 502 + 聚合错误信息
