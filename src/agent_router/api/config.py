from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Awaitable, Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from agent_router.config import has_unresolved_env_var


_MODEL_PRICE_FIELDS = (
    "input_price_per_million",
    "output_price_per_million",
    "cache_read_price_per_million",
    "cache_write_price_per_million",
)


def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


def _is_key_masked(api_key: str) -> bool:
    """检查 api_key 是否为空、占位符或已脱敏."""
    if not api_key or api_key == "${PLACEHOLDER}":
        return True
    if re.match(r"^\*+$", api_key):
        return True
    # _mask_key 产物: 前4 + 星号 + 后4
    if len(api_key) > 8:
        middle = api_key[4:-4]
        if middle and all(c == "*" for c in middle):
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


def _validate_sticky_pins(data: dict[str, Any]) -> None:
    """Reject sticky configurations whose model pins are missing or stale."""
    router = data.get("router")
    if not isinstance(router, dict) or router.get("mode") != "sticky":
        return

    models = data.get("models", {})
    if not isinstance(models, dict):
        raise HTTPException(400, "无法切换到 sticky 模式：models 配置格式无效")

    for model_name, entry in models.items():
        if not isinstance(entry, dict):
            raise HTTPException(
                400,
                f"无法切换到 sticky 模式：模型 '{model_name}' 未指定 pin；"
                "请设置 pinned_provider 和 pinned_model",
            )

        pinned_provider = entry.get("pinned_provider")
        pinned_model = entry.get("pinned_model")
        if not pinned_provider or not pinned_model:
            raise HTTPException(
                400,
                f"无法切换到 sticky 模式：模型 '{model_name}' 未指定 pin；"
                "请设置 pinned_provider 和 pinned_model",
            )

        refs = entry.get("providers", [])
        pin_exists = isinstance(refs, list) and any(
            isinstance(ref, dict)
            and ref.get("provider") == pinned_provider
            and ref.get("model") == pinned_model
            for ref in refs
        )
        if not pin_exists:
            raise HTTPException(
                400,
                f"无法切换到 sticky 模式：模型 '{model_name}' 指定的 pin "
                f"'{pinned_provider}:{pinned_model}' 不在 provider 链中",
            )


def _read_config_raw(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        raise HTTPException(500, f"配置文件不存在: {config_path}")
    with open(path, "rb") as f:
        return tomllib.load(f)


def _toml_escape(s: str) -> str:
    """转义 TOML basic string 中的特殊字符."""
    return (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def _toml_key(name: str) -> str:
    """返回正确引用的 TOML key，处理含 . [] 等的名称."""
    if re.match(r"^[A-Za-z0-9_-]+$", name):
        return name
    return f'"{_toml_escape(name)}"'


def _toml_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return f'"{_toml_escape(v)}"'
    if isinstance(v, (int, float)):
        return str(v)
    return f'"{_toml_escape(str(v))}"'


def _write_toml(config_path: str, data: dict) -> None:
    """将结构化配置原子写入 TOML 文件."""
    lines: list[str] = []

    # [server]
    server = data.get("server", {})
    lines.append("[server]")
    for k, v in server.items():
        if v is None:
            continue
        lines.append(f"{k} = {_toml_value(v)}")
    lines.append("")

    # [router]
    router = data.get("router")
    if router:
        lines.append("[router]")
        for k, v in router.items():
            if v is None:
                continue
            lines.append(f"{k} = {_toml_value(v)}")
        lines.append("")

    # [providers.*]
    providers = data.get("providers", {})
    for name, pdata in providers.items():
        lines.append(f"[providers.{_toml_key(name)}]")
        for k, v in pdata.items():
            if v is None:
                continue
            lines.append(f"{k} = {_toml_value(v)}")
        lines.append("")

    # [models.*] + [[models.*.providers]]
    models = data.get("models", {})
    for vname, entry in models.items():
        key = _toml_key(vname)
        # 新格式: {pinned_*, providers: [...]}；旧格式 list 仍可写入
        if isinstance(entry, list):
            pinned_provider = None
            pinned_model = None
            refs = entry
        elif isinstance(entry, dict) and "providers" in entry:
            pinned_provider = entry.get("pinned_provider")
            pinned_model = entry.get("pinned_model")
            refs = entry.get("providers") or []
        else:
            # 意外结构：跳过
            continue

        # 空 provider 链不写裸 [models.x]，否则热重载会因空模型失败
        if not refs:
            continue

        lines.append(f"[models.{key}]")
        if pinned_provider:
            lines.append(f"pinned_provider = {_toml_value(pinned_provider)}")
        if pinned_model:
            lines.append(f"pinned_model = {_toml_value(pinned_model)}")
        lines.append("")

        for ref in refs:
            lines.append(f"[[models.{key}.providers]]")
            for k, v in ref.items():
                if v is None:
                    continue
                lines.append(f"{k} = {_toml_value(v)}")
            lines.append("")

    content = "\n".join(lines) + "\n"
    tmp_path = Path(config_path).with_suffix(".tmp")
    try:
        # TOML 规范要求 UTF-8；显式指定避免在中文 Windows（默认 cp936/GBK）
        # 上把非 ASCII 内容写成 GBK，导致下方 tomllib 校验回读失败
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
        # 验证写入的 TOML 可解析
        with open(tmp_path, "rb") as f:
            tomllib.load(f)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    tmp_path.replace(config_path)


def create_config_router(
    config_path: str,
    reload_config_fn: Callable[[], Awaitable[None]] | None = None,
) -> APIRouter:
    router = APIRouter(tags=["config"])

    @router.get("/api/config")
    async def get_config():
        """返回完整配置（api_key 脱敏）."""
        raw = _read_config_raw(config_path)
        safe = deepcopy(raw)
        for pname, pdata in safe.get("providers", {}).items():
            if "api_key" in pdata:
                pdata.update(_safe_key_fields(str(pdata["api_key"])))
        return safe

    @router.get("/api/config/providers")
    async def list_providers():
        """列出所有 provider（脱敏）."""
        raw = _read_config_raw(config_path)
        result: dict[str, dict] = {}
        for pname, pdata in raw.get("providers", {}).items():
            result[pname] = {
                "type": pdata.get("type", "anthropic"),
                "base_url": pdata.get("base_url", ""),
                "timeout_seconds": pdata.get("timeout_seconds", 120.0),
                **_safe_key_fields(str(pdata.get("api_key", ""))),
            }
        return result

    @router.get("/api/config/models")
    async def list_models():
        """列出所有虚拟模型及其 provider 链（含 pinned）."""
        raw = _read_config_raw(config_path)
        models = raw.get("models", {})
        result: dict[str, dict] = {}
        for vname, entry in models.items():
            if isinstance(entry, list):
                refs = entry
                pinned_provider = None
                pinned_model = None
            elif isinstance(entry, dict):
                refs = entry.get("providers", [])
                pinned_provider = entry.get("pinned_provider")
                pinned_model = entry.get("pinned_model")
            else:
                continue
            result[vname] = {
                "pinned_provider": pinned_provider,
                "pinned_model": pinned_model,
                "providers": [
                    {
                        "provider": r["provider"],
                        "model": r["model"],
                        "priority": r["priority"],
                        **{
                            field: r[field]
                            for field in _MODEL_PRICE_FIELDS
                            if field in r
                        },
                    }
                    for r in sorted(refs, key=lambda r: r.get("priority", 99))
                ],
            }
        return result

    @router.put("/api/config")
    async def update_config(body: dict):
        """全量更新配置并写回 config.toml.

        api_key 为空或脱敏值时保留原有值，防止误覆盖.
        缺少 router/models 段时合并已有配置，防止误丢失.
        sticky 模式会在写盘前校验每个模型的 pin.
        """
        try:
            existing = _read_config_raw(config_path)
            body = deepcopy(body)

            # 合并缺失段：server、router、providers、models
            for section in ("server", "router", "providers", "models"):
                if section not in body:
                    body[section] = existing.get(section, {})

            _validate_sticky_pins(body)

            # api_key 脱敏值保留原有值
            existing_providers = existing.get("providers", {})
            for pname, pdata in body.get("providers", {}).items():
                api_key = pdata.get("api_key", "")
                if _is_key_masked(api_key):
                    if pname in existing_providers:
                        pdata["api_key"] = existing_providers[pname].get(
                            "api_key", api_key
                        )
                    else:
                        raise HTTPException(
                            400,
                            f"新建 provider '{pname}' 需要提供有效的 api_key",
                        )

            _write_toml(config_path, body)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f"写入配置失败: {e}")

        # 热重载
        if reload_config_fn is not None:
            try:
                await reload_config_fn()
            except Exception as e:
                raise HTTPException(500, f"配置已写入但热重载失败: {e}")

        return {"status": "ok", "message": "配置已更新并热重载"}

    return router
