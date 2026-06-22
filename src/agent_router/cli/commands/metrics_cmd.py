from __future__ import annotations

import typer

from agent_router.cli.async_util import run_async
from agent_router.cli.context import CliContext
from agent_router.cli.output import emit
from agent_router.db import CallStore


async def _with_store(db_path: str):
    store = CallStore(db_path)
    await store.init()
    return store


metrics_app = typer.Typer(help="调用统计")


@metrics_app.command("summary")
def summary(ctx: typer.Context) -> None:
    """调用概览统计."""
    cli: CliContext = ctx.obj

    async def _run():
        store = await _with_store(cli.db)
        try:
            return await store.summary()
        finally:
            await store.close()

    emit(run_async(_run()), cli.output)


@metrics_app.command("by-model")
def by_model(ctx: typer.Context) -> None:
    """按虚拟模型分组统计."""
    cli: CliContext = ctx.obj

    async def _run():
        store = await _with_store(cli.db)
        try:
            return await store.by_model()
        finally:
            await store.close()

    emit(run_async(_run()), cli.output)


@metrics_app.command("by-provider")
def by_provider(ctx: typer.Context) -> None:
    """按 provider 分组统计."""
    cli: CliContext = ctx.obj

    async def _run():
        store = await _with_store(cli.db)
        try:
            return await store.by_provider()
        finally:
            await store.close()

    emit(run_async(_run()), cli.output)


@metrics_app.command("by-real-model")
def by_real_model(ctx: typer.Context) -> None:
    """按真实模型分组统计."""
    cli: CliContext = ctx.obj

    async def _run():
        store = await _with_store(cli.db)
        try:
            return await store.by_real_model()
        finally:
            await store.close()

    emit(run_async(_run()), cli.output)


@metrics_app.command("daily")
def daily(
    ctx: typer.Context,
    days: int = typer.Option(30, "--days", "-d", min=1, max=365),
) -> None:
    """每日调用趋势."""
    cli: CliContext = ctx.obj

    async def _run():
        store = await _with_store(cli.db)
        try:
            return await store.daily_trend(days)
        finally:
            await store.close()

    emit(run_async(_run()), cli.output)
