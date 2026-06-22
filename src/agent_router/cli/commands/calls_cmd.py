from __future__ import annotations

import asyncio
import sys

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
    page: int = typer.Option(1, "--page", min=1),
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

    async def _run() -> None:
        store = await _with_store(cli.db)
        try:
            if not follow:
                calls, _ = await store.list_calls(page=1, size=lines)
                emit(calls, cli.output)
                return
            # follow 模式: 单连接常驻（避免每轮新建事件循环 + sqlite 连接 + 重跑 schema）；
            # 有界去重；瞬时查询错误（如 sqlite database is locked）跳过本轮而非整个 tail 崩溃。
            seen: dict[str, None] = {}
            seen_cap = max(lines * 4, 64)
            while True:
                try:
                    calls, _ = await store.list_calls(page=1, size=lines)
                except Exception as e:
                    print(f"tail: 查询失败，跳过本轮: {e}", file=sys.stderr)
                    await asyncio.sleep(interval)
                    continue
                # list_calls 按 timestamp DESC 返回，倒序后按 旧→新 顺序输出新增项
                for call in reversed(calls):
                    cid = call["id"]
                    if cid in seen:
                        continue
                    emit(call, cli.output)
                    seen[cid] = None
                    if len(seen) > seen_cap:
                        del seen[next(iter(seen))]
                await asyncio.sleep(interval)
        finally:
            await store.close()

    run_async(_run())
