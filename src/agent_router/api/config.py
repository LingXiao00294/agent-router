from __future__ import annotations

from collections.abc import Awaitable, Callable
from copy import deepcopy

from fastapi import APIRouter, HTTPException

from agent_router.config_service import (
    ConfigFileError,
    get_config_masked,
    is_key_masked,
    list_models_raw,
    list_providers_masked,
    read_config_raw,
    write_toml,
)


def create_config_router(
    config_path: str,
    reload_config_fn: Callable[[], Awaitable[None]] | None = None,
) -> APIRouter:
    router = APIRouter(tags=["config"])

    @router.get("/api/config")
    async def get_config():
        """返回完整配置（api_key 脱敏）."""
        try:
            return get_config_masked(config_path)
        except ConfigFileError as e:
            raise HTTPException(500, e.message) from e

    @router.get("/api/config/providers")
    async def list_providers():
        """列出所有 provider（脱敏）."""
        try:
            return list_providers_masked(config_path)
        except ConfigFileError as e:
            raise HTTPException(500, e.message) from e

    @router.get("/api/config/models")
    async def list_models():
        """列出所有虚拟模型及其 provider 链."""
        try:
            return list_models_raw(config_path)
        except ConfigFileError as e:
            raise HTTPException(500, e.message) from e

    @router.put("/api/config")
    async def update_config(body: dict):
        """全量更新配置并写回 config.toml.

        api_key 为空或脱敏值时保留原有值，防止误覆盖.
        缺少 router/models 段时合并已有配置，防止误丢失.
        """
        try:
            existing = read_config_raw(config_path)
            body = deepcopy(body)

            for section in ("server", "router", "providers", "models"):
                if section not in body:
                    body[section] = existing.get(section, {})

            existing_providers = existing.get("providers", {})
            for pname, pdata in body.get("providers", {}).items():
                api_key = pdata.get("api_key", "")
                if is_key_masked(api_key):
                    if pname in existing_providers:
                        pdata["api_key"] = existing_providers[pname].get(
                            "api_key", api_key
                        )
                    else:
                        raise HTTPException(
                            400,
                            f"新建 provider '{pname}' 需要提供有效的 api_key",
                        )

            write_toml(config_path, body)
        except HTTPException:
            raise
        except ConfigFileError as e:
            raise HTTPException(500, e.message) from e
        except Exception as e:
            raise HTTPException(500, f"写入配置失败: {e}") from e

        if reload_config_fn is not None:
            try:
                await reload_config_fn()
            except Exception as e:
                raise HTTPException(500, f"配置已写入但热重载失败: {e}") from e

        return {"status": "ok", "message": "配置已更新并热重载"}

    return router
