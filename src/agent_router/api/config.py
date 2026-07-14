from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Awaitable, Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from agent_router.config import AppConfig, ConfigError, has_unresolved_env_var
from agent_router.config import parse_config_data


def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


def _is_key_masked(api_key: str) -> bool:
    """检查 api_key 是否为空、占位符或已脱敏。"""
    if not api_key or api_key == "${PLACEHOLDER}":
        return True
    if re.match(r"^\*+$", api_key):
        return True
    if len(api_key) > 8:
        middle = api_key[4:-4]
        if middle and all(char == "*" for char in middle):
            return True
    return False


def _safe_key_fields(api_key: str) -> dict[str, object]:
    expanded = os.path.expandvars(api_key)
    unresolved = has_unresolved_env_var(expanded)
    has_key = bool(expanded) and not unresolved
    return {
        "api_key": "" if unresolved else _mask_key(expanded),
        "has_key": has_key,
        "api_key_unresolved": unresolved,
    }


def _read_config_raw(config_path: str) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        raise HTTPException(500, f"配置文件不存在: {config_path}")
    try:
        with path.open("rb") as file:
            return tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise HTTPException(500, f"读取配置失败: {exc}") from exc


def _toml_escape(value: str) -> str:
    """转义 TOML basic string 中的特殊字符。"""
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def _toml_key(name: str) -> str:
    """返回正确引用的 TOML key，处理含点号或方括号的名称。"""
    if re.match(r"^[A-Za-z0-9_-]+$", name):
        return name
    return f'"{_toml_escape(name)}"'


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{_toml_escape(value)}"'
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        fields = ", ".join(
            f"{_toml_key(str(key))} = {_toml_value(item)}"
            for key, item in value.items()
            if item is not None
        )
        return f"{{ {fields} }}"
    raise TypeError(f"不支持的 TOML 值类型: {type(value).__name__}")


def _append_simple_fields(
    lines: list[str], data: dict[str, Any], *, excluded: set[str] | None = None
) -> None:
    excluded = excluded or set()
    for key, value in data.items():
        if key in excluded or value is None:
            continue
        lines.append(f"{_toml_key(str(key))} = {_toml_value(value)}")


def _serialize_toml(data: dict[str, Any]) -> str:
    """将规范配置序列化为目标 TOML 格式，不执行文件写入。"""
    lines: list[str] = []

    lines.append("[server]")
    _append_simple_fields(lines, data.get("server", {}))
    lines.append("")

    lines.append("[router]")
    _append_simple_fields(lines, data.get("router", {}))
    lines.append("")

    providers = data.get("providers", {})
    for provider_name, provider in providers.items():
        provider_key = _toml_key(str(provider_name))
        lines.append(f"[providers.{provider_key}]")
        _append_simple_fields(lines, provider, excluded={"models"})
        lines.append("")

        for model_name, actual_model in provider.get("models", {}).items():
            model_key = _toml_key(str(model_name))
            lines.append(f"[providers.{provider_key}.models.{model_key}]")
            _append_simple_fields(lines, actual_model)
            lines.append("")

    for virtual_name, virtual_model in data.get("models", {}).items():
        virtual_key = _toml_key(str(virtual_name))
        lines.append(f"[models.{virtual_key}]")
        pinned_model = virtual_model.get("pinned_model")
        if pinned_model is not None:
            lines.append(f"pinned_model = {_toml_value(pinned_model)}")
        lines.append("models = [")
        for model_ref in virtual_model.get("models", []):
            lines.append(f"  {_toml_value(model_ref)},")
        lines.append("]")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _replace_file(path: Path, content: bytes) -> None:
    """通过同目录临时文件原子替换配置，并保证不遗留临时文件。"""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        # 调用方传入显式 UTF-8 编码后的字节，避免受 Windows 默认编码影响。
        tmp_path.write_bytes(content)
        tmp_path.replace(path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _references_by_identity(
    raw: dict[str, Any],
) -> dict[tuple[str, str], set[str]]:
    references: dict[tuple[str, str], set[str]] = {}
    models = raw.get("models", {})
    if not isinstance(models, dict):
        return references
    for virtual_name, virtual_model in models.items():
        if not isinstance(virtual_model, dict):
            continue
        refs = list(virtual_model.get("models", []))
        pinned_model = virtual_model.get("pinned_model")
        if isinstance(pinned_model, dict):
            refs.append(pinned_model)
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            provider = ref.get("provider")
            model = ref.get("model")
            if isinstance(provider, str) and isinstance(model, str):
                references.setdefault((provider, model), set()).add(str(virtual_name))
    return references


def _deletion_conflict(
    existing: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any] | None:
    """返回必须分两次保存的 Provider 或实际模型删除冲突。"""
    existing_providers = existing.get("providers", {})
    candidate_providers = candidate.get("providers", {})
    references = _references_by_identity(existing)

    for provider in sorted(set(existing_providers) - set(candidate_providers)):
        referenced_by = sorted(
            {
                virtual_name
                for (provider_name, _), names in references.items()
                if provider_name == provider
                for virtual_name in names
            }
        )
        if referenced_by:
            return {
                "code": "provider_in_use",
                "provider": provider,
                "referenced_by": referenced_by,
            }

    for provider in sorted(set(existing_providers) & set(candidate_providers)):
        existing_models = existing_providers[provider].get("models", {})
        candidate_models = candidate_providers[provider].get("models", {})
        for model in sorted(set(existing_models) - set(candidate_models)):
            referenced_by = sorted(references.get((provider, model), set()))
            if referenced_by:
                return {
                    "code": "model_in_use",
                    "provider": provider,
                    "model": model,
                    "referenced_by": referenced_by,
                }
    return None


def _merge_and_preserve_keys(
    body: dict[str, Any], existing: dict[str, Any]
) -> dict[str, Any]:
    candidate = deepcopy(body)
    for section in ("server", "router", "providers", "models"):
        if section not in candidate:
            candidate[section] = deepcopy(existing.get(section, {}))

    existing_providers = existing.get("providers", {})
    providers = candidate.get("providers", {})
    if not isinstance(providers, dict):
        raise ConfigError("providers 必须是对象")
    for provider_name, provider in providers.items():
        if not isinstance(provider, dict):
            raise ConfigError(f"Provider '{provider_name}' 配置必须是对象")
        provider.pop("has_key", None)
        provider.pop("api_key_unresolved", None)
        api_key = str(provider.get("api_key", ""))
        if not _is_key_masked(api_key):
            continue
        if provider_name not in existing_providers:
            raise ConfigError(f"新建 Provider '{provider_name}' 需要提供有效的 api_key")
        provider["api_key"] = existing_providers[provider_name].get("api_key", api_key)
    return candidate


def _safe_config(raw: dict[str, Any]) -> dict[str, Any]:
    safe = deepcopy(raw)
    for provider in safe.get("providers", {}).values():
        if "api_key" in provider:
            provider.update(_safe_key_fields(str(provider["api_key"])))
    return safe


def create_config_router(
    config_path: str,
    reload_config_fn: Callable[[AppConfig], Awaitable[None]] | None = None,
) -> APIRouter:
    """创建配置读取与原子更新 API。"""
    router = APIRouter(tags=["config"])

    @router.get("/api/config")
    async def get_config():
        """返回完整规范配置，并对 api_key 脱敏。"""
        return _safe_config(_read_config_raw(config_path))

    @router.get("/api/config/providers")
    async def list_providers():
        """返回包含实际模型目录的 Provider 配置，并对 api_key 脱敏。"""
        raw = _safe_config(_read_config_raw(config_path))
        return raw.get("providers", {})

    @router.get("/api/config/models")
    async def list_models():
        """返回有序 ModelRef 与单一结构化 pinned_model。"""
        return deepcopy(_read_config_raw(config_path).get("models", {}))

    @router.put("/api/config")
    async def update_config(body: dict[str, Any]):
        """校验候选配置，原子写回 TOML，并以失败回滚保证状态一致。"""
        path = Path(config_path)
        existing = _read_config_raw(config_path)
        original_bytes = path.read_bytes()

        try:
            candidate = _merge_and_preserve_keys(body, existing)
            conflict = _deletion_conflict(existing, candidate)
            if conflict is not None:
                return JSONResponse(status_code=409, content={"error": conflict})
            runtime_config = parse_config_data(
                candidate, allow_unresolved_api_keys=True
            )
            content = _serialize_toml(candidate)
            round_trip = tomllib.loads(content)
            runtime_config = parse_config_data(
                round_trip, allow_unresolved_api_keys=True
            )
        except ConfigError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (TypeError, ValueError, tomllib.TOMLDecodeError) as exc:
            raise HTTPException(400, f"配置序列化失败: {exc}") from exc

        try:
            _replace_file(path, content.encode("utf-8"))
        except OSError as exc:
            raise HTTPException(500, f"写入配置失败，旧配置保持不变: {exc}") from exc

        if reload_config_fn is not None:
            try:
                await reload_config_fn(runtime_config)
            except Exception as exc:
                try:
                    _replace_file(path, original_bytes)
                except OSError as rollback_exc:
                    raise HTTPException(
                        500,
                        "运行时切换失败，且配置文件回滚失败: "
                        f"{exc}; rollback: {rollback_exc}",
                    ) from exc
                raise HTTPException(
                    500, f"运行时切换失败，配置文件与运行时已回滚: {exc}"
                ) from exc

        return {"status": "ok", "message": "配置已更新并热重载"}

    return router
