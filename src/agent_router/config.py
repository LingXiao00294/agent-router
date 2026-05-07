from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ProviderDef(BaseModel):
    """Provider 基础定义 — 每个 provider 只配置一次."""

    type: Literal["anthropic", "openai"]
    api_key: str
    base_url: str
    timeout_seconds: float = 120.0

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
    """解析后的 provider 配置 (ProviderDef + ModelProviderRef 合并).

    供 routing.py 和 providers 使用，外部无需关心此类型。
    """

    type: Literal["anthropic", "openai"]
    model: str
    api_key: str
    base_url: str
    priority: int
    timeout_seconds: float = 120.0

    @field_validator("base_url")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8080
    log_level: Literal["debug", "info", "warning", "error"] = "info"


class AppConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    models: dict[str, list[ProviderConfig]]


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


def load_config(config_path: str | Path) -> AppConfig:
    path = Path(config_path)
    if not path.exists():
        print(f"错误: 配置文件不存在: {path}", file=sys.stderr)
        sys.exit(1)

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    raw = _expand_env_vars(raw)

    server_raw = raw.get("server", {})
    providers_raw: dict[str, dict] = raw.get("providers", {})
    models_raw: dict[str, list[dict]] = raw.get("models", {})

    if not providers_raw:
        print("错误: 配置文件中未定义任何 provider (providers 为空)", file=sys.stderr)
        sys.exit(1)

    if not models_raw:
        print("错误: 配置文件中未定义任何模型 (models 为空)", file=sys.stderr)
        sys.exit(1)

    # 解析 provider 基础定义
    providers: dict[str, ProviderDef] = {}
    for name, pdata in providers_raw.items():
        try:
            providers[name] = ProviderDef(**pdata)
        except Exception as e:
            print(f"错误: 解析 provider '{name}' 配置失败: {e}", file=sys.stderr)
            sys.exit(1)

    # 解析模型引用，合并为 ProviderConfig
    models: dict[str, list[ProviderConfig]] = {}
    for virtual_name, refs in models_raw.items():
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
                    ProviderConfig(
                        type=pdef.type,
                        model=ref["model"],
                        api_key=pdef.api_key,
                        base_url=pdef.base_url,
                        priority=ref["priority"],
                        timeout_seconds=pdef.timeout_seconds,
                    )
                )
            except KeyError as e:
                print(
                    f"错误: 模型 '{virtual_name}' 第 {i + 1} 条缺少 {e} 字段",
                    file=sys.stderr,
                )
                sys.exit(1)

        if not resolved:
            print(
                f"警告: 模型 '{virtual_name}' 没有有效的 provider，已跳过",
                file=sys.stderr,
            )
            continue
        resolved.sort(key=lambda p: p.priority)
        models[virtual_name] = resolved

    return AppConfig(
        server=ServerConfig(**server_raw),
        models=models,
    )
