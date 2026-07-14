from __future__ import annotations

import os
import re
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

# 运行日志默认值（ServerConfig 与 monitoring.setup_logging 共用，避免多处字面量漂移）。
DEFAULT_LOG_FILE = "logs/agent-router.log"
DEFAULT_LOG_MAX_BYTES = 10_000_000
DEFAULT_LOG_BACKUP_COUNT = 5
_UNRESOLVED_ENV_RE = re.compile(r"\$\{[^}]+}")
_PRICE_FIELDS = (
    "input_price_per_million",
    "output_price_per_million",
    "cache_read_price_per_million",
    "cache_write_price_per_million",
)


class ConfigError(ValueError):
    """表示配置文件无法解析为当前版本的结构化配置。"""


def has_unresolved_env_var(value: str) -> bool:
    """Return True when os.path.expandvars left ${ENV_VAR} references unresolved."""
    return bool(_UNRESOLVED_ENV_RE.search(value))


class ActualModelDef(BaseModel):
    """Provider 目录中的实际模型定义。"""

    model_config = ConfigDict(extra="forbid")

    input_price_per_million: float | None = None
    output_price_per_million: float | None = None
    cache_read_price_per_million: float | None = None
    cache_write_price_per_million: float | None = None

    @field_validator(*_PRICE_FIELDS)
    @classmethod
    def non_negative_price(cls, value: float | None) -> float | None:
        """Validate that configured token prices are non-negative."""
        if value is not None and value < 0:
            raise ValueError("模型费用必须大于等于 0")
        return value


class ProviderDef(BaseModel):
    """Provider 连接设置及其实际模型目录。"""

    model_config = ConfigDict(extra="forbid")

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
    models: dict[str, ActualModelDef] = Field(default_factory=dict)

    @field_validator("api_key")
    @classmethod
    def api_key_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("api_key 不能为空")
        return value

    @field_validator("base_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("max_concurrent", "max_queue")
    @classmethod
    def non_negative_int(cls, value: int) -> int:
        if value < 0:
            raise ValueError("必须大于等于 0")
        return value

    @field_validator("queue_wait_timeout", "rate_limit_cooldown")
    @classmethod
    def positive_float(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("必须大于 0")
        return value

    @field_validator("models")
    @classmethod
    def actual_model_names_must_not_be_blank(
        cls, models: dict[str, ActualModelDef]
    ) -> dict[str, ActualModelDef]:
        blank_names = [name for name in models if not name.strip()]
        if blank_names:
            raise ValueError("实际模型名不能为空")
        return models


class ModelRef(BaseModel):
    """以结构化字段标识一个 Provider 下的实际模型。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str
    model: str

    @field_validator("provider", "model")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("不能为空")
        return value


class VirtualModelDef(BaseModel):
    """配置文件中的虚拟模型及其有序实际模型引用。"""

    model_config = ConfigDict(extra="forbid")

    pinned_model: ModelRef | None = None
    models: list[ModelRef] = Field(min_length=1)

    @field_validator("models")
    @classmethod
    def model_refs_must_be_unique(cls, refs: list[ModelRef]) -> list[ModelRef]:
        seen: set[tuple[str, str]] = set()
        for ref in refs:
            identity = (ref.provider, ref.model)
            if identity in seen:
                raise ValueError(f"不能重复引用实际模型 '{ref.provider}/{ref.model}'")
            seen.add(identity)
        return refs


class ProviderConfig(BaseModel):
    """Provider 连接设置、实际模型价格与运行时优先级的解析结果。"""

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
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator(*_PRICE_FIELDS)
    @classmethod
    def non_negative_price(cls, value: float | None) -> float | None:
        """Validate that configured token prices are non-negative."""
        if value is not None and value < 0:
            raise ValueError("模型费用必须大于等于 0")
        return value


class VirtualModelConfig(BaseModel):
    """Router 直接消费的虚拟模型运行时配置。"""

    pinned_model: ModelRef | None = None
    providers: list[ProviderConfig]


class ServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = "127.0.0.1"
    port: int = 9456
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    # 运行日志本地文件（相对 cwd）；为空则只输出到 stdout。
    log_file: str = DEFAULT_LOG_FILE
    log_max_bytes: int = DEFAULT_LOG_MAX_BYTES
    log_backup_count: int = DEFAULT_LOG_BACKUP_COUNT


class RouterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failure_threshold: int = 5
    recovery_timeout: float = 600.0
    # failover=按数组顺序故障转移；sticky=各虚拟模型只使用 pinned_model。
    mode: Literal["failover", "sticky"] = "sticky"


class ConfigDocument(BaseModel):
    """TOML 配置真源对应的领域模型。"""

    model_config = ConfigDict(extra="forbid")

    server: ServerConfig = Field(default_factory=ServerConfig)
    router: RouterConfig = Field(default_factory=RouterConfig)
    providers: dict[str, ProviderDef] = Field(default_factory=dict)
    models: dict[str, VirtualModelDef] = Field(default_factory=dict)


class AppConfig(BaseModel):
    """完成实际模型解析后供运行时组件消费的配置。"""

    server: ServerConfig = Field(default_factory=ServerConfig)
    router: RouterConfig = Field(default_factory=RouterConfig)
    providers: dict[str, ProviderDef] = Field(default_factory=dict)
    models: dict[str, VirtualModelConfig]


def _expand_env_vars(raw: Any) -> Any:
    """递归展开配置中所有字符串值的 ${ENV_VAR} 引用。"""
    if isinstance(raw, str):
        return os.path.expandvars(raw)
    if isinstance(raw, dict):
        return {key: _expand_env_vars(value) for key, value in raw.items()}
    if isinstance(raw, list):
        return [_expand_env_vars(item) for item in raw]
    return raw


def _reject_legacy_model_format(raw: dict[str, Any]) -> None:
    models = raw.get("models", {})
    if not isinstance(models, dict):
        return
    for virtual_name, entry in models.items():
        if isinstance(entry, list) or (
            isinstance(entry, dict)
            and any(
                field in entry for field in ("providers", "pinned_provider", "priority")
            )
        ):
            raise ConfigError(
                f"模型 '{virtual_name}' 使用旧版配置格式；"
                "请改用 models = [{{ provider = ..., model = ... }}] "
                "和结构化 pinned_model，旧格式不再兼容"
            )


def parse_config_document(raw: dict[str, Any]) -> ConfigDocument:
    """将已读取的 TOML 字典校验为当前版本配置文档。

    Args:
        raw: 未展开环境变量的 TOML 字典。

    Returns:
        校验完成且环境变量已展开的配置文档。

    Raises:
        ConfigError: 配置使用旧格式、包含未知字段或字段值无效。
    """
    _reject_legacy_model_format(raw)
    try:
        return ConfigDocument.model_validate(_expand_env_vars(deepcopy(raw)))
    except ValidationError as exc:
        raise ConfigError(f"配置校验失败: {exc}") from exc


def _provider_config_from_def(
    provider: ProviderDef,
    actual_model: ActualModelDef,
    *,
    name: str,
    model: str,
    priority: int,
) -> ProviderConfig:
    return ProviderConfig(
        type=provider.type,
        name=name,
        model=model,
        api_key=provider.api_key,
        base_url=provider.base_url,
        priority=priority,
        timeout_seconds=provider.timeout_seconds,
        failure_threshold=provider.failure_threshold,
        recovery_timeout=provider.recovery_timeout,
        max_concurrent=provider.max_concurrent,
        max_queue=provider.max_queue,
        queue_wait_timeout=provider.queue_wait_timeout,
        rate_limit_cooldown=provider.rate_limit_cooldown,
        **actual_model.model_dump(),
    )


def build_runtime_config(
    document: ConfigDocument, *, allow_unresolved_api_keys: bool = False
) -> AppConfig:
    """解析实际模型引用并构建 Router 可直接消费的配置。

    Args:
        document: 已通过字段校验的配置文档。
        allow_unresolved_api_keys: 是否允许运行时保留未展开的 API key 占位符。

    Returns:
        包含完整 ProviderConfig 链的运行时配置。

    Raises:
        ConfigError: 引用悬空、sticky pin 无效或 API key 未解析。
    """
    if not allow_unresolved_api_keys:
        unresolved = [
            name
            for name, provider in document.providers.items()
            if has_unresolved_env_var(provider.api_key)
        ]
        if unresolved:
            names = ", ".join(sorted(unresolved))
            raise ConfigError(f"Provider API key 环境变量未设置或未正确插值: {names}")

    actual_model_index = {
        (provider_name, model_name): (provider, actual_model)
        for provider_name, provider in document.providers.items()
        for model_name, actual_model in provider.models.items()
    }
    resolved_models: dict[str, VirtualModelConfig] = {}
    for virtual_name, virtual_model in document.models.items():
        providers: list[ProviderConfig] = []
        for index, ref in enumerate(virtual_model.models):
            provider = document.providers.get(ref.provider)
            if provider is None:
                raise ConfigError(
                    f"模型 '{virtual_name}' 引用了未知 Provider '{ref.provider}'"
                )
            indexed_model = actual_model_index.get((ref.provider, ref.model))
            if indexed_model is None:
                raise ConfigError(
                    f"模型 '{virtual_name}' 引用了未在 Provider '{ref.provider}' "
                    f"下定义的实际模型 '{ref.model}'"
                )
            provider, actual_model = indexed_model
            providers.append(
                _provider_config_from_def(
                    provider,
                    actual_model,
                    name=ref.provider,
                    model=ref.model,
                    priority=index + 1,
                )
            )

        pin = virtual_model.pinned_model
        if document.router.mode == "sticky":
            if pin is None:
                raise ConfigError(
                    f"全局 sticky 模式下模型 '{virtual_name}' 必须设置 pinned_model"
                )
            if pin not in virtual_model.models:
                raise ConfigError(
                    f"模型 '{virtual_name}' 的 pinned_model "
                    f"'{pin.provider}/{pin.model}' 不在该虚拟模型的模型链中"
                )

        resolved_models[virtual_name] = VirtualModelConfig(
            pinned_model=pin,
            providers=providers,
        )

    return AppConfig(
        server=document.server,
        router=document.router,
        providers=document.providers,
        models=resolved_models,
    )


def parse_config_data(
    raw: dict[str, Any], *, allow_unresolved_api_keys: bool = False
) -> AppConfig:
    """校验原始配置字典并构建运行时配置。"""
    document = parse_config_document(raw)
    return build_runtime_config(
        document, allow_unresolved_api_keys=allow_unresolved_api_keys
    )


def load_config(
    config_path: str | Path, *, allow_unresolved_api_keys: bool = False
) -> AppConfig:
    """从 TOML 文件加载并解析运行时配置。

    Raises:
        ConfigError: 文件不存在、TOML 无法解析或配置语义无效。
    """
    path = Path(config_path)
    if not path.exists():
        raise ConfigError(f"配置文件不存在: {path}")

    try:
        with path.open("rb") as file:
            raw = tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"读取配置文件失败: {path}: {exc}") from exc

    return parse_config_data(raw, allow_unresolved_api_keys=allow_unresolved_api_keys)
