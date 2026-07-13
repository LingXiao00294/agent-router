from __future__ import annotations

import os
import re
import sys
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# 运行日志默认值（ServerConfig 与 monitoring.setup_logging 共用，避免多处字面量漂移）。
DEFAULT_LOG_FILE = "logs/agent-router.log"
DEFAULT_LOG_MAX_BYTES = 10_000_000
DEFAULT_LOG_BACKUP_COUNT = 5
_UNRESOLVED_ENV_RE = re.compile(r"\$\{[^}]+}")


def has_unresolved_env_var(value: str) -> bool:
    """Return True when os.path.expandvars left ${ENV_VAR} references unresolved."""
    return bool(_UNRESOLVED_ENV_RE.search(value))


class ProviderDef(BaseModel):
    """Provider 基础定义 — 每个 provider 只配置一次."""

    type: Literal["anthropic", "openai"]
    api_key: str
    base_url: str
    timeout_seconds: float = 120.0
    failure_threshold: int | None = None
    recovery_timeout: float | None = None
    # 本地限流：0 = 不限制 / 不排队（保持旧行为）
    max_concurrent: int = 0
    max_queue: int = 0
    queue_wait_timeout: float = 30.0
    rate_limit_cooldown: float = 30.0

    @field_validator("api_key")
    @classmethod
    def api_key_must_not_be_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("api_key 不能为空")
        return v

    @field_validator("base_url")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("max_concurrent", "max_queue")
    @classmethod
    def non_negative_int(cls, v: int) -> int:
        if v < 0:
            raise ValueError("必须大于等于 0")
        return v

    @field_validator("queue_wait_timeout", "rate_limit_cooldown")
    @classmethod
    def positive_float(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("必须大于 0")
        return v


class ProviderConfig(BaseModel):
    """解析后的 provider 配置 (ProviderDef + ModelProviderRef 合并).

    供 routing.py 和 providers 使用，外部无需关心此类型。
    """

    type: Literal["anthropic", "openai"]
    name: str = ""
    model: str
    api_key: str
    base_url: str
    priority: int
    timeout_seconds: float = 120.0
    failure_threshold: int | None = None
    recovery_timeout: float | None = None
    max_concurrent: int = 0
    max_queue: int = 0
    queue_wait_timeout: float = 30.0
    rate_limit_cooldown: float = 30.0
    input_price_per_million: float | None = None
    output_price_per_million: float | None = None
    cache_read_price_per_million: float | None = None
    cache_write_price_per_million: float | None = None

    @field_validator("base_url")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator(
        "input_price_per_million",
        "output_price_per_million",
        "cache_read_price_per_million",
        "cache_write_price_per_million",
    )
    @classmethod
    def non_negative_price(cls, v: float | None) -> float | None:
        """Validate that configured token prices are non-negative."""
        if v is not None and v < 0:
            raise ValueError("模型费用必须大于等于 0")
        return v


class VirtualModelConfig(BaseModel):
    """虚拟模型：可选指定 provider + provider 链.

    pinned_* 在全局 router.mode=sticky 时生效；failover 模式下保留但不使用。
    """

    pinned_provider: str | None = None
    pinned_model: str | None = None
    providers: list[ProviderConfig]

    @model_validator(mode="after")
    def validate_pin_pair(self) -> VirtualModelConfig:
        """为缺失的 pin 选择第一优先级模型，并校验 pin 成对出现。"""
        if not self.pinned_provider and not self.pinned_model:
            if self.providers:
                first = min(self.providers, key=lambda provider: provider.priority)
                self.pinned_provider = first.name
                self.pinned_model = first.model
            return self
        if not self.pinned_provider or not self.pinned_model:
            raise ValueError("pinned_provider 与 pinned_model 必须同时设置")
        return self


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 9456
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    # 运行日志本地文件（相对 cwd）；为空则只输出到 stdout。
    log_file: str = DEFAULT_LOG_FILE
    log_max_bytes: int = DEFAULT_LOG_MAX_BYTES
    log_backup_count: int = DEFAULT_LOG_BACKUP_COUNT


class RouterConfig(BaseModel):
    failure_threshold: int = 5
    recovery_timeout: float = 600.0
    # 全局路由模式：failover=按 priority 故障转移；sticky=各虚拟模型钉死 pinned 项
    mode: Literal["failover", "sticky"] = "sticky"


class AppConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    router: RouterConfig = Field(default_factory=RouterConfig)
    models: dict[str, VirtualModelConfig]


def _expand_env_vars(raw: dict) -> dict:
    """递归展开字典中所有字符串值的 ${ENV_VAR} 引用."""

    def expand(value):
        if isinstance(value, str):
            return os.path.expandvars(value)
        if isinstance(value, dict):
            return {k: expand(v) for k, v in value.items()}
        if isinstance(value, list):
            return [expand(item) for item in value]
        return value

    return expand(raw)


def _provider_config_from_def(
    pdef: ProviderDef,
    *,
    name: str,
    model: str,
    priority: int,
    input_price_per_million: float | None = None,
    output_price_per_million: float | None = None,
    cache_read_price_per_million: float | None = None,
    cache_write_price_per_million: float | None = None,
) -> ProviderConfig:
    return ProviderConfig(
        type=pdef.type,
        name=name,
        model=model,
        api_key=pdef.api_key,
        base_url=pdef.base_url,
        priority=priority,
        timeout_seconds=pdef.timeout_seconds,
        failure_threshold=pdef.failure_threshold,
        recovery_timeout=pdef.recovery_timeout,
        max_concurrent=pdef.max_concurrent,
        max_queue=pdef.max_queue,
        queue_wait_timeout=pdef.queue_wait_timeout,
        rate_limit_cooldown=pdef.rate_limit_cooldown,
        input_price_per_million=input_price_per_million,
        output_price_per_million=output_price_per_million,
        cache_read_price_per_million=cache_read_price_per_million,
        cache_write_price_per_million=cache_write_price_per_million,
    )


def _resolve_provider_refs(
    virtual_name: str,
    refs: list[dict],
    providers: dict[str, ProviderDef],
) -> list[ProviderConfig]:
    """将模型引用列表合并为 ProviderConfig 列表."""
    if not isinstance(refs, list) or not refs:
        print(f"错误: 模型 '{virtual_name}' 的 provider 列表为空", file=sys.stderr)
        sys.exit(1)

    resolved: list[ProviderConfig] = []
    for i, ref in enumerate(refs):
        provider_name = ref.get("provider", "")
        if not provider_name:
            print(
                f"错误: 模型 '{virtual_name}' 第 {i + 1} 条缺少 provider 字段",
                file=sys.stderr,
            )
            sys.exit(1)
        if provider_name not in providers:
            print(
                f"警告: 模型 '{virtual_name}' 引用了未知 provider '{provider_name}'，已自动跳过",
                file=sys.stderr,
            )
            continue

        pdef = providers[provider_name]
        try:
            resolved.append(
                _provider_config_from_def(
                    pdef,
                    name=provider_name,
                    model=ref["model"],
                    priority=ref["priority"],
                    input_price_per_million=ref.get("input_price_per_million"),
                    output_price_per_million=ref.get("output_price_per_million"),
                    cache_read_price_per_million=ref.get(
                        "cache_read_price_per_million"
                    ),
                    cache_write_price_per_million=ref.get(
                        "cache_write_price_per_million"
                    ),
                )
            )
        except KeyError as e:
            print(
                f"错误: 模型 '{virtual_name}' 第 {i + 1} 条缺少 {e} 字段",
                file=sys.stderr,
            )
            sys.exit(1)

    if not resolved:
        return []
    resolved.sort(key=lambda p: p.priority)
    return resolved


def load_config(
    config_path: str | Path, *, allow_unresolved_api_keys: bool = False
) -> AppConfig:
    path = Path(config_path)
    if not path.exists():
        print(f"错误: 配置文件不存在: {path}", file=sys.stderr)
        sys.exit(1)

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    raw = _expand_env_vars(raw)

    server_raw = raw.get("server", {})
    router_raw = raw.get("router", {})
    providers_raw: dict[str, dict] = raw.get("providers", {})
    models_raw: dict = raw.get("models", {})

    if not providers_raw:
        print(
            "提示: 配置文件中未定义任何 provider，可通过 dashboard 添加",
            file=sys.stderr,
        )

    if not models_raw:
        print("提示: 配置文件中未定义任何模型，可通过 dashboard 添加", file=sys.stderr)

    # 解析 provider 基础定义
    providers: dict[str, ProviderDef] = {}
    for name, pdata in providers_raw.items():
        try:
            provider = ProviderDef(**pdata)
            if not allow_unresolved_api_keys and has_unresolved_env_var(
                provider.api_key
            ):
                raise ValueError(f"环境变量未设置或未正确插值: {provider.api_key}")
            providers[name] = provider
        except Exception as e:
            print(f"错误: 解析 provider '{name}' 配置失败: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        router_cfg = RouterConfig(**router_raw)
    except Exception as e:
        print(f"错误: 解析 [router] 配置失败: {e}", file=sys.stderr)
        sys.exit(1)

    # 解析模型：兼容旧 list 格式与新 dict 格式
    models: dict[str, VirtualModelConfig] = {}
    for virtual_name, entry in models_raw.items():
        pinned_provider: str | None = None
        pinned_model: str | None = None
        refs: list[dict]

        if isinstance(entry, list):
            refs = entry
        elif isinstance(entry, dict):
            # 兼容旧版 per-model mode 字段（已迁移到 [router].mode，此处忽略）
            pinned_provider = entry.get("pinned_provider")
            pinned_model = entry.get("pinned_model")
            refs = entry.get("providers", [])
            if not isinstance(refs, list):
                print(
                    f"错误: 模型 '{virtual_name}' 的 providers 必须是数组",
                    file=sys.stderr,
                )
                sys.exit(1)
        else:
            print(
                f"错误: 模型 '{virtual_name}' 配置格式无效",
                file=sys.stderr,
            )
            sys.exit(1)

        resolved = _resolve_provider_refs(virtual_name, refs, providers)
        if not resolved:
            print(
                f"警告: 模型 '{virtual_name}' 没有有效的 provider，已跳过",
                file=sys.stderr,
            )
            continue

        try:
            models[virtual_name] = VirtualModelConfig(
                pinned_provider=pinned_provider,
                pinned_model=pinned_model,
                providers=resolved,
            )
        except Exception as e:
            print(f"错误: 解析模型 '{virtual_name}' 失败: {e}", file=sys.stderr)
            sys.exit(1)

    if router_cfg.mode == "sticky":
        for vname, vm in models.items():
            if not vm.pinned_provider or not vm.pinned_model:
                print(
                    f"错误: 全局 sticky 模式下模型 '{vname}' 必须设置 "
                    "pinned_provider 与 pinned_model",
                    file=sys.stderr,
                )
                sys.exit(1)
            matched = any(
                p.name == vm.pinned_provider and p.model == vm.pinned_model
                for p in vm.providers
            )
            if not matched:
                print(
                    f"错误: 模型 '{vname}' 的 pinned provider "
                    f"'{vm.pinned_provider}:{vm.pinned_model}' "
                    "不在该虚拟模型的 provider 链中",
                    file=sys.stderr,
                )
                sys.exit(1)

    return AppConfig(
        server=ServerConfig(**server_raw),
        router=router_cfg,
        models=models,
    )
