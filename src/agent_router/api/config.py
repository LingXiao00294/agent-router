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

    # [[models.*]]
    models = data.get("models", {})
    for vname, refs in models.items():
        for ref in refs:
            lines.append(f"[[models.{_toml_key(vname)}]]")
            for k, v in ref.items():
                if v is None:
                    continue
                lines.append(f"{k} = {_toml_value(v)}")
            lines.append("")

    content = "\n".join(lines) + "\n"
    tmp_path = Path(config_path).with_suffix(".tmp")
    try:
        with open(tmp_path, "w") as f:
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
        """列出所有虚拟模型及其 provider 链."""
        raw = _read_config_raw(config_path)
        models = raw.get("models", {})
        result: dict[str, list[dict]] = {}
        for vname, refs in models.items():
            result[vname] = [
                {
                    "provider": r["provider"],
                    "model": r["model"],
                    "priority": r["priority"],
                }
                for r in sorted(refs, key=lambda r: r.get("priority", 99))
            ]
        return result

    @router.put("/api/config")
    async def update_config(body: dict):
        """全量更新配置并写回 config.toml.

        api_key 为空或脱敏值时保留原有值，防止误覆盖.
        缺少 router/models 段时合并已有配置，防止误丢失.
        """
        try:
            existing = _read_config_raw(config_path)
            body = deepcopy(body)

            # 合并缺失段：server、router、providers、models
            for section in ("server", "router", "providers", "models"):
                if section not in body:
                    body[section] = existing.get(section, {})

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
