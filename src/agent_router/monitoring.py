from __future__ import annotations

import logging
import sys

import structlog


def setup_logging(level: str = "info") -> None:
    """配置结构化日志.

    开发模式 (level=debug): 彩色控制台输出
    生产模式 (level=info): JSON 结构化输出
    """

    log_level = getattr(logging, level.upper(), logging.INFO)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=False),
    ]

    if log_level <= logging.DEBUG:
        # 开发模式: 彩色控制台
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(log_level),
            cache_logger_on_first_use=True,
        )
    else:
        # 生产模式: JSON
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(log_level),
            cache_logger_on_first_use=True,
        )

    # 配置标准库日志桥接
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=log_level,
    )
