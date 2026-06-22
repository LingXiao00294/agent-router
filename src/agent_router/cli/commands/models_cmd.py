from __future__ import annotations

import typer

from agent_router.cli.context import CliContext
from agent_router.cli.output import emit
from agent_router.config import load_config

models_app = typer.Typer(help="虚拟模型")


@models_app.command("list")
def list_models(ctx: typer.Context) -> None:
    """列出虚拟模型（Anthropic List Models 格式）."""
    cli: CliContext = ctx.obj
    config = load_config(cli.config)
    data = {
        "data": [
            {
                "id": name,
                "type": "model",
                "display_name": name,
                "created_at": "2025-01-01T00:00:00Z",
            }
            for name in config.models
        ]
    }
    emit(data, cli.output)
