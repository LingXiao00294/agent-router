from __future__ import annotations

import json
import logging

import pytest
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

from agent_router import monitoring


def _last_json_line(text: str) -> dict:
    """提取输出最后一行非空内容并解析为 JSON。"""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return json.loads(lines[-1])


@pytest.fixture(autouse=True)
def _isolate_logging():
    """每个测试前后清理 structlog / contextvars 全局状态，避免相互污染。"""
    clear_contextvars()
    yield
    structlog.reset_defaults()


def test_json_output_in_production(capsys):
    monitoring.setup_logging("info")
    structlog.get_logger("test").info("biz.event", model="glm")

    data = _last_json_line(capsys.readouterr().out)
    assert data["event"] == "biz.event"
    assert data["model"] == "glm"
    assert data["level"] == "info"
    assert data["timestamp"].endswith("Z")  # UTC ISO


def test_console_output_in_debug(capsys):
    monitoring.setup_logging("debug")
    structlog.get_logger("test").info("biz.event", model="glm")

    out = capsys.readouterr().out
    # ConsoleRenderer 输出为彩色文本而非 JSON。
    with pytest.raises(json.JSONDecodeError):
        json.loads(out.strip().splitlines()[-1])
    assert "biz.event" in out


def test_sensitive_data_redacted(capsys):
    monitoring.setup_logging("info")
    structlog.get_logger("test").info(
        "leak.test",
        api_key="sk-1234567890abcdef",
        nested={"authorization": "Bearer supersecret", "safe": 1},
    )

    out = capsys.readouterr().out
    data = _last_json_line(out)
    assert "sk-1234567890abcdef" not in out
    assert "supersecret" not in out
    assert "***" in data["api_key"]
    assert "***" in data["nested"]["authorization"]
    assert data["nested"]["safe"] == 1


def test_request_id_via_contextvars(capsys):
    monitoring.setup_logging("info")
    bind_contextvars(request_id="req-abc-123")
    structlog.get_logger("test").info("ctx.event")
    clear_contextvars()

    data = _last_json_line(capsys.readouterr().out)
    assert data["request_id"] == "req-abc-123"


def test_stdlib_logging_is_structured(capsys):
    """第三方库（uvicorn/httpx 等）走 stdlib logging 的日志也被结构化为 JSON。"""
    monitoring.setup_logging("info")
    logging.getLogger("uvicorn.access").info("GET /health 200")

    data = _last_json_line(capsys.readouterr().out)
    assert data["event"] == "GET /health 200"
    assert data["level"] == "info"
    assert "timestamp" in data
    # ProcessorFormatter 的内部元数据字段不应泄露到输出。
    assert "_record" not in data
    assert "_from_structlog" not in data


def test_reconfigure_logging_switches_level(capsys):
    """热重载：切换到 warning 后，info 级别日志被过滤。"""
    monitoring.setup_logging("info")
    log = structlog.get_logger("test")

    monitoring.reconfigure_logging("warning")
    log.info("should.be.filtered")
    log.warning("should.appear")

    out = capsys.readouterr().out
    assert "should.be.filtered" not in out
    assert "should.appear" in out
