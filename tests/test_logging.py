from __future__ import annotations

import json
import logging
import time

import pytest
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

from agent_router import monitoring


def _last_json_line(text: str) -> dict:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return json.loads(lines[-1])


def _flush() -> None:
    for h in logging.getLogger().handlers:
        h.flush()


@pytest.fixture(autouse=True)
def _isolate_logging():
    """每个测试前后清理 contextvars / structlog / root handler（释放文件句柄）。"""
    clear_contextvars()
    yield
    root = logging.getLogger()
    for h in list(root.handlers):
        h.close()
        root.removeHandler(h)
    structlog.reset_defaults()


def test_file_output_is_full_json(tmp_path):
    log_file = tmp_path / "app.log"
    monitoring.setup_logging("info", log_file=str(log_file))
    structlog.get_logger("t").info("biz.event", model="glm", error="x" * 200)

    _flush()
    data = _last_json_line(log_file.read_text(encoding="utf-8"))
    assert data["event"] == "biz.event"
    assert data["model"] == "glm"
    assert data["error"] == "x" * 200  # 文件中长字段完整不截断
    assert data["level"] == "info"
    assert data["timestamp"].endswith("Z")  # UTC ISO


def test_stdout_is_brief_not_json(tmp_path, capsys):
    monitoring.setup_logging("info", log_file=str(tmp_path / "app.log"))
    structlog.get_logger("t").info("biz.event", model="glm")

    out = capsys.readouterr().out
    # stdout 走彩色 ConsoleRenderer，不产生 JSON 行。
    assert not any(line.lstrip().startswith("{") for line in out.splitlines())
    assert "biz.event" in out


def test_stdout_truncates_long_fields_and_folds_errors(tmp_path, capsys):
    monitoring.setup_logging("info", log_file=str(tmp_path / "app.log"))
    structlog.get_logger("t").error(
        "failover.exhausted",
        model="m",
        attempts=2,
        errors=[{"provider": "a", "error": "e1"}, {"provider": "b", "error": "e2"}],
    )

    out = capsys.readouterr().out
    # stdout: errors 列表折叠为摘要。
    assert "2 条" in out and "详见日志文件" in out
    # 文件: errors 保持完整数组。
    _flush()
    data = _last_json_line((tmp_path / "app.log").read_text(encoding="utf-8"))
    assert isinstance(data["errors"], list)
    assert len(data["errors"]) == 2


def test_sensitive_data_redacted_in_file(tmp_path):
    log_file = tmp_path / "app.log"
    monitoring.setup_logging("info", log_file=str(log_file))
    structlog.get_logger("t").info(
        "leak.test",
        api_key="sk-1234567890abcdef",
        nested={"authorization": "Bearer supersecret", "safe": 1},
    )

    _flush()
    raw = log_file.read_text(encoding="utf-8")
    assert "sk-1234567890abcdef" not in raw
    assert "supersecret" not in raw
    data = _last_json_line(raw)
    assert "***" in data["api_key"]
    assert "***" in data["nested"]["authorization"]
    assert data["nested"]["safe"] == 1


def test_request_id_via_contextvars(tmp_path):
    log_file = tmp_path / "app.log"
    monitoring.setup_logging("info", log_file=str(log_file))
    bind_contextvars(request_id="req-abc-123")
    structlog.get_logger("t").info("ctx.event")
    clear_contextvars()

    _flush()
    data = _last_json_line(log_file.read_text(encoding="utf-8"))
    assert data["request_id"] == "req-abc-123"


def test_stdlib_logging_structured_in_file(tmp_path):
    log_file = tmp_path / "app.log"
    monitoring.setup_logging("info", log_file=str(log_file))
    logging.getLogger("uvicorn.access").info("GET /health 200")

    _flush()
    data = _last_json_line(log_file.read_text(encoding="utf-8"))
    assert data["event"] == "GET /health 200"
    assert data["level"] == "info"
    assert "timestamp" in data
    assert "_record" not in data and "_from_structlog" not in data


def test_reconfigure_logging_switches_level(tmp_path):
    log_file = tmp_path / "app.log"
    monitoring.setup_logging("info", log_file=str(log_file))
    log = structlog.get_logger("t")

    monitoring.reconfigure_logging("warning", log_file=str(log_file))
    log.info("should.be.filtered")
    log.warning("should.appear")

    _flush()
    raw = log_file.read_text(encoding="utf-8")
    assert "should.be.filtered" not in raw
    assert "should.appear" in raw


def test_log_file_optional_stdout_only(tmp_path, capsys):
    """log_file 为空时只输出到 stdout，不创建文件 handler。"""
    monitoring.setup_logging("info", log_file="")
    structlog.get_logger("t").info("biz.event", model="glm")

    out = capsys.readouterr().out
    assert "biz.event" in out
    # 仅 stdout handler，无文件 handler。
    assert not any(
        isinstance(h, logging.FileHandler) for h in logging.getLogger().handlers
    )


async def test_streaming_request_id_propagates(tmp_path):
    """回归：流式 request_id 须贯穿到 routing 层日志，即使中间件已清理上下文。

    真实时序下（uvicorn），StreamingResponse 的 body 在中间件
    ``clear_contextvars`` 之后才被 ASGI 消费；若 routing 层仅依赖 contextvars，
    会 fallback 到新 uuid 与 ``http.request`` 断链。本测试复现该时序：先
    ``clear_contextvars`` 模拟中间件已返回，再消费由 ``_stream_wrapper`` 包裹
    的 ``route_stream``，断言 routing 层日志仍拿到端点显式传入的 request_id。
    """
    import httpx

    from agent_router.app import _stream_wrapper
    from agent_router.config import AppConfig, ProviderConfig, ServerConfig
    from agent_router.db import CallStore
    from agent_router.routing import Router

    log_file = tmp_path / "app.log"
    monitoring.setup_logging("info", log_file=str(log_file))

    sse = (
        b'event: message_start\n'
        b'data: {"message":{"usage":{"input_tokens":10}}}\n\n'
        b'event: message_delta\n'
        b'data: {"usage":{"output_tokens":5}}\n\n'
        b'event: message_stop\n'
        b'data: {}\n\n'
    )
    mock_transport = httpx.MockTransport(
        lambda req: httpx.Response(200, content=sse)
    )
    http_client = httpx.AsyncClient(transport=mock_transport)

    config = AppConfig(
        server=ServerConfig(host="127.0.0.1", port=9456),
        models={
            "vm": [
                ProviderConfig(
                    type="anthropic",
                    name="anthropic",
                    model="claude-haiku-4-5",
                    api_key="sk-ant-test",
                    base_url="https://api.anthropic.com",
                    priority=1,
                )
            ]
        },
    )
    router_engine = Router(config, http_client)
    store = CallStore(str(tmp_path / "calls.db"))
    await store.init()

    # 模拟中间件在返回 StreamingResponse 后已清理上下文（真实 uvicorn 时序）。
    clear_contextvars()
    try:
        outcome: dict = {}
        body = {"model": "vm", "stream": True, "max_tokens": 100,
                "messages": [{"role": "user", "content": "hi"}]}
        async for _ in _stream_wrapper(
            router_engine.route_stream(body, outcome),
            outcome=outcome,
            store=store,
            virtual_model="vm",
            request_body=body,
            start_time=time.time(),
            request_id="REQ-FIX-123",
        ):
            pass
    finally:
        await http_client.aclose()
        await store.close()

    _flush()
    raw = log_file.read_text(encoding="utf-8")
    starts = [
        json.loads(ln) for ln in raw.splitlines()
        if '"request.start"' in ln and '"stream": true' in ln
    ]
    assert starts, "routing 层未记录流式 request.start 日志"
    assert all(d.get("request_id") == "REQ-FIX-123" for d in starts), (
        f"流式 routing 层 request_id 未贯穿: {[d.get('request_id') for d in starts]}"
    )

