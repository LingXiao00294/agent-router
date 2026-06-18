from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.contextvars import merge_contextvars
from structlog.dev import ConsoleRenderer
from structlog.processors import (
    JSONRenderer,
    StackInfoRenderer,
    TimeStamper,
    add_log_level,
    format_exc_info,
)
from structlog.stdlib import LoggerFactory, ProcessorFormatter

# 需要脱敏的字段名（按小写匹配），命中即对值脱敏。
_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "token",
        "password",
        "passwd",
        "secret",
        "x-api-key",
        "set-cookie",
    }
)

# 脱敏后保留的前缀 / 后缀长度。
_KEEP_PREFIX = 4
_KEEP_SUFFIX = 2


def _redact(value: Any) -> str:
    """脱敏单个值：保留前 4 + 后 2 字符，中间以 *** 代替；过短则全 ***。"""
    s = str(value)
    if len(s) <= _KEEP_PREFIX + _KEEP_SUFFIX:
        return "***"
    return f"{s[:_KEEP_PREFIX]}***{s[-_KEEP_SUFFIX:]}"


def _is_sensitive(key: Any) -> bool:
    return isinstance(key, str) and key.lower() in _SENSITIVE_KEYS


def _scrub(obj: Any) -> Any:
    """递归脱敏 dict / list 中键名敏感的字段（值脱敏，键名保留）。

    快速路径：当前层级既无敏感键又无嵌套容器时原样返回，避免在无敏感内容的
    高频日志上逐键重建字典。
    """
    if isinstance(obj, dict):
        if not any(
            _is_sensitive(k) or isinstance(v, (dict, list)) for k, v in obj.items()
        ):
            return obj
        return {
            k: (_redact(v) if _is_sensitive(k) else _scrub(v)) for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_scrub(item) for item in obj]
    return obj


def redact_secrets(_logger: Any, _name: str, event_dict: dict) -> dict:
    """structlog processor：递归脱敏事件字典中的敏感字段。"""
    return _scrub(event_dict)


def _shared_processors() -> list:
    """structlog 与 stdlib 日志共用的前置 processor 链。"""
    return [
        merge_contextvars,
        add_log_level,
        TimeStamper(fmt="iso", utc=True),
        redact_secrets,
    ]


def setup_logging(level: str = "info") -> None:
    """配置结构化日志，可重复调用（热重载时复用）。

    - debug 级别：彩色控制台输出（开发）
    - info 及以上：JSON 结构化输出（生产）
    - 经 ProcessorFormatter 统一桥接 stdlib / uvicorn 等第三方库日志到同一渲染管线
    - 输出到 stdout，敏感字段自动脱敏，时间戳为 UTC ISO
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    is_json = log_level > logging.DEBUG

    # 清除 structlog 全局配置与缓存，确保重复调用（含新日志级别）即时生效。
    structlog.reset_defaults()

    renderer = JSONRenderer() if is_json else ConsoleRenderer(colors=True)
    renderer_processors = [
        ProcessorFormatter.remove_processors_meta,
        StackInfoRenderer(),
        format_exc_info,
        renderer,
    ]

    # structlog 自身日志：经 shared_processors 后包装成 LogRecord，
    # 交给 ProcessorFormatter 统一渲染（与 stdlib 日志走同一出口）。
    structlog.configure(
        processors=[*_shared_processors(), ProcessorFormatter.wrap_for_formatter],
        logger_factory=LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        # 关闭缓存，保证运行时热切换日志级别对所有 logger 实例生效。
        cache_logger_on_first_use=False,
    )

    # foreign（stdlib）日志先走 foreign_pre_chain，再与 structlog 日志一起走 renderer。
    formatter = ProcessorFormatter(
        foreign_pre_chain=_shared_processors(),
        processors=renderer_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    # force=True 移除既有 handler 重新配置 root，避免热重载时 handler 累积。
    logging.basicConfig(handlers=[handler], level=log_level, force=True)


def reconfigure_logging(level: str) -> None:
    """运行时热切换日志级别（供 PUT /api/config 热重载调用）。"""
    setup_logging(level)
