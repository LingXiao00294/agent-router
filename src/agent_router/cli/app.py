from __future__ import annotations

from importlib.metadata import version
from typing import Literal

import typer
from dotenv import load_dotenv

from agent_router.cli.commands.calls_cmd import calls_app
from agent_router.cli.commands.config_cmd import config_app
from agent_router.cli.commands.health_cmd import run_health
from agent_router.cli.commands.metrics_cmd import metrics_app
from agent_router.cli.commands.models_cmd import models_app
from agent_router.cli.commands.serve import run_serve
from agent_router.cli.context import CliContext

app = typer.Typer(
    name="agent-router",
    help="Agent Router - 本地 LLM API 路由代理",
    invoke_without_command=True,
    no_args_is_help=False,
)

app.add_typer(config_app, name="config")
app.add_typer(metrics_app, name="metrics")
app.add_typer(calls_app, name="calls")
app.add_typer(models_app, name="models")


@app.callback()
def main(
    ctx: typer.Context,
    config: str = typer.Option("config.toml", "--config", "-c", help="配置文件路径"),
    db: str = typer.Option("calls.db", "--db", help="调用记录数据库路径"),
    output: Literal["json", "table"] = typer.Option(
        "table", "--output", "-o", help="输出格式: json 或 table"
    ),
    host: str | None = typer.Option(None, "--host", help="覆盖 server.host"),
    port: int | None = typer.Option(None, "--port", "-p", help="覆盖 server.port"),
) -> None:
    """Agent Router CLI."""
    # 所有子命令统一注入 .env（若存在），使 config validate / models list 等非启动
    # 命令也能展开 ${VAR}；.env 非必须，缺失时仅相关 provider 被跳过，工具仍可启动。
    load_dotenv()
    ctx.obj = CliContext(
        config=config,
        db=db,
        output=output,
        host=host,
        port=port,
    )
    if ctx.invoked_subcommand is None:
        run_serve(ctx.obj)


@app.command("version")
def version_cmd() -> None:
    """显示版本号."""
    typer.echo(version("agent-router"))


@app.command("health")
def health_cmd(
    ctx: typer.Context,
    deep: bool = typer.Option(False, "--deep", help="深度检查（含数据库）"),
) -> None:
    """健康检查."""
    run_health(ctx.obj, deep=deep)


@app.command("serve")
def serve_cmd(ctx: typer.Context) -> None:
    """启动 HTTP 服务."""
    run_serve(ctx.obj)
