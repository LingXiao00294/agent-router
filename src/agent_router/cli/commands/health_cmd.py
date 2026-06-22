from __future__ import annotations

from typing import Any

import typer

from agent_router.cli.async_util import run_async
from agent_router.cli.context import CliContext
from agent_router.cli.output import emit
from agent_router.config import validate_config
from agent_router.db import CallStore


def run_health(ctx: CliContext, *, deep: bool = False) -> None:
    """健康检查."""
    result: dict[str, Any] = {"status": "ok", "config": ctx.config}
    validation = validate_config(ctx.config)
    if not validation.ok:
        result = {
            "status": "error",
            "config": ctx.config,
            "errors": validation.errors,
        }
        emit(result, ctx.output)
        raise typer.Exit(code=1)

    if validation.warnings:
        result["warnings"] = validation.warnings

    if deep:
        async def _check_db():
            store = CallStore(ctx.db)
            await store.init()
            try:
                summary = await store.summary()
                return {"db": ctx.db, "summary": summary}
            finally:
                await store.close()

        result["database"] = run_async(_check_db())

    emit(result, ctx.output)
