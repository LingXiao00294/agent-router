from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

DEFAULT_LOG_FILE = "logs/agent-router.log"
DEFAULT_LOG_MAX_BYTES = 10_000_000
DEFAULT_LOG_BACKUP_COUNT = 5


class ProviderDef(BaseModel):
    """Provider 基础定义 — 每个 provider 只配置一次."""

    type: Literal["anthropic", "openai"]
    api_key: str
    base_url: str
    timeout_seconds: float = 120.0
    failure_threshold: int | None = None
    recovery_timeout: float | None = None

    @field_validator("api_key")
    @classmethod
    def api_key_must_not_be_empty_or_unresolved(cls, v: str) -> str:
        if not v or v.startswith("${"):
            raise ValueError(f"环境变量未设置或未正确插值: {v}")
        return v

    @field_validator("base_url")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")


class ProviderConfig(BaseModel):
    """解析后的 provider 配置 (ProviderDef + ModelProviderRef 合并)."""

    type: Literal["anthropic", "openai"]
    name: str = ""
    model: str
    api_key: str
    base_url: str
    priority: int
    timeout_seconds: float = 120.0
    failure_threshold: int | None = None
    recovery_timeout: float | None = None

    @field_validator("base_url")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 9456
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    log_file: str = DEFAULT_LOG_FILE
    log_max_bytes: int = DEFAULT_LOG_MAX_BYTES
    log_backup_count: int = DEFAULT_LOG_BACKUP_COUNT


class RouterConfig(BaseModel):
    failure_threshold: int = 5
    recovery_timeout: float = 600.0


class AppConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    router: RouterConfig = Field(default_factory=RouterConfig)
    models: dict[str, list[ProviderConfig]]


class ConfigError(Exception):
    """配置加载或校验失败."""

    def __init__(self, errors: list[str], warnings: list[str] | None = None) -> None:
        self.errors = errors
        self.warnings = warnings or []
        super().__init__("\n".join(self.errors))


@dataclass
class ValidationResult:
    config: AppConfig | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and self.config is not None


def _expand_env_vars(raw: dict) -> dict:
    def expand(value):
        if isinstance(value, str):
            return os.path.expandvars(value)
        if isinstance(value, dict):
            return {k: expand(v) for k, v in value.items()}
        if isinstance(value, list):
            return [expand(item) for item in value]
        return value
    return expand(raw)


def validate_config(config_path: str | Path) -> ValidationResult:
    path = Path(config_path)
    if not path.exists():
        return ValidationResult(errors=[f"配置文件不存在: {path}"])
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        return ValidationResult(errors=[f"TOML 解析失败: {e}"])
    return _parse_config(raw)


def _parse_config(raw: dict) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    raw = _expand_env_vars(raw)
    server_raw = raw.get("server", {})
    router_raw = raw.get("router", {})
    providers_raw: dict[str, dict] = raw.get("providers", {})
    models_raw: dict[str, list[dict]] = raw.get("models", {})
    if not providers_raw:
        warnings.append("配置文件中未定义任何 provider，可通过 dashboard 添加")
    if not models_raw:
        warnings.append("配置文件中未定义任何模型，可通过 dashboard 添加")
    providers: dict[str, ProviderDef] = {}
    for name, pdata in providers_raw.items():
        try:
            providers[name] = ProviderDef(**pdata)
        except Exception as e:
            errors.append(f"解析 provider \'{name}\' 配置失败: {e}")
    if errors:
        return ValidationResult(errors=errors, warnings=warnings)
    models: dict[str, list[ProviderConfig]] = {}
    for virtual_name, refs in models_raw.items():
        if not isinstance(refs, list) or not refs:
            errors.append(f"模型 \'{virtual_name}\' 的 provider 列表为空")
            continue
        resolved: list[ProviderConfig] = []
        for i, ref in enumerate(refs):
            provider_name = ref.get("provider", "")
            if not provider_name:
                errors.append(f"模型 \'{virtual_name}\' 第 {i + 1} 条缺少 provider 字段")
                continue
            if provider_name not in providers:
                warnings.append(
                    f"模型 \'{virtual_name}\' 引用了未知 provider \'{provider_name}\'，已自动跳过"
                )
                continue
            pdef = providers[provider_name]
            try:
                resolved.append(ProviderConfig(
                    type=pdef.type, name=provider_name, model=ref["model"],
                    api_key=pdef.api_key, base_url=pdef.base_url, priority=ref["priority"],
                    timeout_seconds=pdef.timeout_seconds,
                    failure_threshold=pdef.failure_threshold,
                    recovery_timeout=pdef.recovery_timeout,
                ))
            except KeyError as e:
                errors.append(f"模型 \'{virtual_name}\' 第 {i + 1} 条缺少 {e} 字段")
        if not resolved:
            warnings.append(f"模型 \'{virtual_name}\' 没有有效的 provider，已跳过")
            continue
        resolved.sort(key=lambda p: p.priority)
        models[virtual_name] = resolved
    if errors:
        return ValidationResult(errors=errors, warnings=warnings)
    return ValidationResult(
        config=AppConfig(
            server=ServerConfig(**server_raw),
            router=RouterConfig(**router_raw),
            models=models,
        ),
        warnings=warnings,
    )


def load_config(config_path: str | Path) -> AppConfig:
    result = validate_config(config_path)
    if not result.ok:
        raise ConfigError(result.errors, result.warnings)
    assert result.config is not None
    return result.config


def resolved_config_view(config: AppConfig) -> dict:
    global_ft = config.router.failure_threshold
    global_rt = config.router.recovery_timeout
    models_view: dict[str, list[dict]] = {}
    for vname, chain in config.models.items():
        models_view[vname] = [
            {
                "provider": p.name, "model": p.model, "priority": p.priority,
                "type": p.type, "base_url": p.base_url,
                "timeout_seconds": p.timeout_seconds,
                "failure_threshold": p.failure_threshold if p.failure_threshold is not None else global_ft,
                "recovery_timeout": p.recovery_timeout if p.recovery_timeout is not None else global_rt,
            }
            for p in chain
        ]
    return {
        "server": config.server.model_dump(),
        "router": config.router.model_dump(),
        "models": models_view,
    }
