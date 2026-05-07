from __future__ import annotations

import os
import re
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException


def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


def _read_config_raw(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        raise HTTPException(500, f"配置文件不存在: {config_path}")
    with open(path, "rb") as f:
        return tomllib.load(f)


def _write_toml(config_path: str, data: dict) -> None:
    """将结构化配置写回 TOML 文件."""
    lines: list[str] = []

    # [server]
    server = data.get("server", {})
    lines.append("[server]")
    for k in ["host", "port", "log_level"]:
        if k in server:
            lines.append(f'{k} = {_toml_value(server[k])}')
    lines.append("")

    # [providers.*]
    providers = data.get("providers", {})
    for name, pdata in providers.items():
        lines.append(f"[providers.{name}]")
        for k in ["type", "api_key", "base_url", "timeout_seconds"]:
            if k in pdata:
                lines.append(f"{k} = {_toml_value(pdata[k])}")
        lines.append("")

    # [[models.*]]
    models = data.get("models", {})
    for vname, refs in models.items():
        for ref in refs:
            lines.append(f"[[models.{vname}]]")
            for k in ["provider", "model", "priority"]:
                if k in ref:
                    lines.append(f"{k} = {_toml_value(ref[k])}")
            lines.append("")

    with open(config_path, "w") as f:
        f.write("\n".join(lines) + "\n")


def _toml_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return f'"{v}"'
    if isinstance(v, (int, float)):
        return str(v)
    return f'"{v}"'


def create_config_router(config_path: str) -> APIRouter:
    router = APIRouter(tags=["config"])

    @router.get("/api/config")
    async def get_config():
        """返回完整配置（api_key 脱敏）."""
        raw = _read_config_raw(config_path)
        safe = deepcopy(raw)
        for pname, pdata in safe.get("providers", {}).items():
            if "api_key" in pdata:
                pdata["api_key"] = _mask_key(pdata["api_key"])
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
                "api_key": _mask_key(pdata.get("api_key", "")),
                "timeout_seconds": pdata.get("timeout_seconds", 120.0),
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
        """全量更新配置并写回 config.toml."""
        try:
            _write_toml(config_path, body)
        except Exception as e:
            raise HTTPException(500, f"写入配置失败: {e}")
        return {"status": "ok", "message": "配置已更新，请重启 router 生效"}

    return router
