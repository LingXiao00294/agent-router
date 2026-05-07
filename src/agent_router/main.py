from __future__ import annotations

import argparse
import sys

import uvicorn
from dotenv import load_dotenv

from agent_router.config import load_config
from agent_router.db import CallStore
from agent_router.monitoring import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agent Router - 本地 LLM API 路由代理",
    )
    parser.add_argument(
        "--config", "-c",
        default="config.toml",
        help="配置文件路径 (默认: config.toml)",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="覆盖配置文件中的 server.host",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=None,
        help="覆盖配置文件中的 server.port",
    )
    parser.add_argument(
        "--db",
        default="calls.db",
        help="调用记录数据库路径 (默认: calls.db)",
    )
    args = parser.parse_args()

    load_dotenv()

    config = load_config(args.config)

    if args.host:
        config.server.host = args.host
    if args.port:
        config.server.port = args.port

    setup_logging(config.server.log_level)

    store = CallStore(args.db)

    # 延迟导入，确保日志已配置
    from agent_router.app import create_app

    app = create_app(config, store)

    print(f"Agent Router 启动: http://{config.server.host}:{config.server.port}")
    print(f"配置文件: {args.config}")
    print(f"数据库: {args.db}")
    print(f"虚拟模型: {', '.join(config.models.keys())}")

    uvicorn.run(
        app,
        host=config.server.host,
        port=config.server.port,
        log_level=config.server.log_level,
        access_log=config.server.log_level == "debug",
    )


if __name__ == "__main__":
    main()
