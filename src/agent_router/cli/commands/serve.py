from __future__ import annotations

import uvicorn

from agent_router.cli.context import CliContext, load_config_or_exit
from agent_router.db import CallStore
from agent_router.monitoring import setup_logging


def run_serve(ctx: CliContext) -> None:
    """启动 HTTP 服务."""
    config = load_config_or_exit(ctx)
    if ctx.host is not None:
        config.server.host = ctx.host
    if ctx.port is not None:
        config.server.port = ctx.port

    setup_logging(
        level=config.server.log_level,
        log_file=config.server.log_file,
        log_max_bytes=config.server.log_max_bytes,
        log_backup_count=config.server.log_backup_count,
    )

    store = CallStore(ctx.db)

    from agent_router.app import create_app

    app = create_app(config, store, config_path=ctx.config)

    print(f"Agent Router 启动: http://{config.server.host}:{config.server.port}")
    print(f"配置文件: {ctx.config}")
    print(f"数据库: {ctx.db}")
    print(f"虚拟模型: {', '.join(config.models.keys())}")

    uvicorn.run(
        app,
        host=config.server.host,
        port=config.server.port,
        log_level=config.server.log_level,
        access_log=False,
        log_config=None,
    )
