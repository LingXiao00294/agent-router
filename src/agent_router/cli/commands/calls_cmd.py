from __future__ import annotations

import time

import typer

from agent_router.cli.async_util import run_async
from agent_router.cli.context import CliContext
from agent_router.cli.output import emit
from agent_router.db import CallStore


async def _with_store(db_path: str):
    store = CallStore(db_path)
    await store.init()
    return store


calls_app = typer.Typer(help="调用记录查询")


@calls_app.command("list")
def list_calls(
    ctx: typer.Context,
    page: int = typer.Option(1, "--page", "-p", min=1),
    size: int = typer.Option(50, "--size", "-s", min=1, max=200),
    model: str | None = typer.Option(None, "--model", "-m"),
    status: str | None = typer.Option(None, "--status"),
) -> None:
    """分页查询调用记录."""
    cli: CliContext = ctx.obj

    async def _run():
        store = await _with_store(cli.db)
        try:
            calls, total = await store.list_calls(
                page=page, size=size, model=model, status=status
            )
            return {
                "data": calls,
                "total": total,
                "page": page,
                "size": size,
                "pages": max(1, (total + size - 1) // size),
            }
        finally:
            await store.close()

    emit(run_async(_run()), cli.output)


@calls_app.command("get")
def get_call(
    ctx: typer.Context,
    call_id: str = typer.Argument(..., help="调用记录 ID"),
) -> None:
    """查询单次调用详情."""
    cli: CliContext = ctx.obj

    async def _run():
        store = await _with_store(cli.db)
        try:
            return await store.get_call(call_id)
        finally:
            await store.close()

    call = run_async(_run())
    if call is None:
        raise typer.Exit(code=1)
    emit(call, cli.output)


@calls_app.command("tail")
def tail_calls(
    ctx: typer.Context,
    lines: int = typer.Option(10, "--lines", "-n", min=1, max=200),
    follow: bool = typer.Option(False, "--follow", "-f"),
    interval: float = typer.Option(2.0, "--interval", min=0.5),
) -> None:
    """显示最近的调用记录."""
    cli: CliContext = ctx.obj
    seen: set[str] = set()

    async def _fetch():
        store = await _with_store(cli.db)
        try:
            calls, _ = await store.list_calls(page=1, size=lines)
            return calls
        finally:
            await store.close()

    while True:
        calls = run_async(_fetch())
        if follow:
            new_calls = [c for c in reversed(calls) if c["id"] not in seen]
            for call in new_calls:
                seen.add(call["id"])
                emit(call, cli.output)
        else:
            emit(calls, cli.output)
            break
        time.sleep(interval)
