from __future__ import annotations

import typer

from agent_router.cli.context import CliContext
from agent_router.cli.output import emit
from agent_router.config import load_config, resolved_config_view, validate_config
from agent_router.config_service import (
    get_config_masked,
    list_models_raw,
    list_providers_masked,
)

config_app = typer.Typer(help="配置查看与校验")


@config_app.command("validate")
def validate(ctx: typer.Context) -> None:
    """校验配置文件."""
    cli: CliContext = ctx.obj
    result = validate_config(cli.config)
    data = {
        "ok": result.ok,
        "errors": result.errors,
        "warnings": result.warnings,
    }
    emit(data, cli.output)
    if not result.ok:
        raise typer.Exit(code=1)


@config_app.command("show")
def show(ctx: typer.Context) -> None:
    """显示完整配置（api_key 脱敏）."""
    cli: CliContext = ctx.obj
    emit(get_config_masked(cli.config), cli.output)


@config_app.command("providers")
def providers(ctx: typer.Context) -> None:
    """列出所有 provider（脱敏）."""
    cli: CliContext = ctx.obj
    emit(list_providers_masked(cli.config), cli.output)


@config_app.command("models")
def models(ctx: typer.Context) -> None:
    """列出虚拟模型及其 provider 链."""
    cli: CliContext = ctx.obj
    emit(list_models_raw(cli.config), cli.output)


@config_app.command("resolved")
def resolved(ctx: typer.Context) -> None:
    """显示解析后的运行时配置视图."""
    cli: CliContext = ctx.obj
    config = load_config(cli.config)
    emit(resolved_config_view(config), cli.output)
