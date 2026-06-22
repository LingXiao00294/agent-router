from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import typer

from agent_router.cli.output import emit
from agent_router.config import AppConfig, ConfigError, load_config


@dataclass
class CliContext:
    config: str
    db: str
    output: Literal["json", "table"]
    host: str | None = None
    port: int | None = None


def load_config_or_exit(ctx: CliContext) -> AppConfig:
    """加载配置；校验失败时 emit 错误并以退出码 1 退出，避免裸 ConfigError traceback。"""
    try:
        return load_config(ctx.config)
    except ConfigError as e:
        emit({"ok": False, "errors": e.errors, "warnings": e.warnings}, ctx.output)
        raise typer.Exit(code=1) from e
