from __future__ import annotations

import json
import re
import time
import uuid
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from structlog.contextvars import bind_contextvars, get_contextvars, unbind_contextvars

from agent_router.api.config import create_config_router
from agent_router.api.metrics import create_metrics_router
from agent_router.config import AppConfig, load_config
from agent_router.db import CallStore
from agent_router.monitoring import reconfigure_logging
from agent_router.routing import AllProvidersFailedError, Router, UnknownModelError

logger = structlog.get_logger(__name__)

# 从 SSE 流中提取 usage 的正则 (message_start 有 input_tokens, message_delta 有 output_tokens)
_SSE_MSG_START_RE = re.compile(
    rb"event:\s*message_start\s*\r?\ndata:\s*(\{.*?\})\s*(?:\r?\n|$)", re.DOTALL
)
_SSE_MSG_DELTA_RE = re.compile(
    rb"event:\s*message_delta\s*\r?\ndata:\s*(\{.*?\})\s*(?:\r?\n|$)", re.DOTALL
)

# 合法 X-Request-ID：仅字母数字与 - _，长度 ≤128；违规则回退到生成的 uuid，
# 避免客户端注入超长/特殊字符污染日志与响应头。
_REQUEST_ID_MAX_LEN = 128
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _sanitize_request_id(raw: str | None) -> str:
    """校验客户端透传的 X-Request-ID，非法则回退到新 uuid。"""
    if raw and _REQUEST_ID_RE.fullmatch(raw):
        return raw
    return str(uuid.uuid4())


def create_app(
    config: AppConfig, store: CallStore, config_path: str = "config.toml"
) -> FastAPI:
    http_client = httpx.AsyncClient(
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
        timeout=httpx.Timeout(300.0, connect=10.0),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await store.init()
        logger.info("server.start", host=config.server.host, port=config.server.port)
        yield
        await http_client.aclose()
        await store.close()
        logger.info("server.shutdown")

    app = FastAPI(
        title="Agent Router",
        description="本地 LLM API 路由代理",
        version="0.1.0",
        lifespan=lifespan,
    )

    router_engine = Router(config, http_client)

    # 注册 metrics API
    metrics_router = create_metrics_router(store)
    app.include_router(metrics_router)

    # 注册 config API
    async def _reload_config() -> None:
        try:
            new_config = load_config(config_path)
        except SystemExit:
            raise RuntimeError("新配置语义无效，旧配置保持不变")
        # 先重载路由配置，成功后再切换日志级别，避免半成功的不一致状态。
        await router_engine.reload_config(new_config)
        reconfigure_logging(
            level=new_config.server.log_level,
            log_file=new_config.server.log_file,
            log_max_bytes=new_config.server.log_max_bytes,
            log_backup_count=new_config.server.log_backup_count,
        )

    config_router = create_config_router(config_path, reload_config_fn=_reload_config)
    app.include_router(config_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/circuit-breaker")
    async def get_circuit_breaker_states():
        """返回所有 provider 的熔断状态."""
        states = await router_engine.circuit_breaker.get_all_states()
        return {name: state.value for name, state in states.items()}

    @app.post("/api/circuit-breaker/{provider}/reset")
    async def reset_circuit_breaker(provider: str):
        """重置指定 provider 的熔断状态."""
        await router_engine.circuit_breaker.reset(provider)
        return {"status": "ok", "provider": provider}

    @app.get("/v1/models")
    async def list_models():
        """Anthropic List Models 格式."""
        return {
            "data": [
                {
                    "id": name,
                    "type": "model",
                    "display_name": name,
                    "created_at": "2025-01-01T00:00:00Z",
                }
                for name in router_engine.model_names
            ]
        }

    @app.post("/v1/messages")
    async def messages(request: Request):
        body = await request.json()
        virtual_model = body.get("model", "unknown")
        is_stream = body.get("stream", False)
        start_time = time.time()
        # 中间件已绑定 request_id；此处显式取出，供流式场景在中间件清理上下文后
        # 仍能把同一 request_id 贯穿到 routing 层日志：StreamingResponse 的 body 在
        # 中间件返回后才被 ASGI 消费，此时中间件已 unbind request_id，
        # routing 层会 fallback 到新 uuid 而与 http.request 日志断链。
        request_id = get_contextvars().get("request_id")

        try:
            if is_stream:
                outcome: dict = {}
                return StreamingResponse(
                    _stream_wrapper(
                        router_engine.route_stream(body, outcome),
                        outcome=outcome,
                        store=store,
                        virtual_model=virtual_model,
                        request_body=body,
                        start_time=start_time,
                        request_id=request_id,
                    ),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    },
                )
            else:
                outcome: dict = {}
                result = await router_engine.route_non_stream(body, outcome)
                latency_ms = int((time.time() - start_time) * 1000)
                usage = result.get("usage", {})
                await store.record(
                    virtual_model=virtual_model,
                    status="success",
                    provider_name=outcome.get("provider_name"),
                    provider_type=outcome.get("provider_type"),
                    provider_model=outcome.get("provider_model"),
                    provider_url=outcome.get("provider_url"),
                    attempt=outcome.get("attempt", 1),
                    latency_ms=latency_ms,
                    request_body=body,
                    response_body=result,
                    input_tokens=usage.get("input_tokens"),
                    output_tokens=usage.get("output_tokens"),
                    cache_read_tokens=usage.get("cache_read_input_tokens"),
                    cache_write_tokens=usage.get("cache_creation_input_tokens"),
                    failover_details=outcome.get("_failures"),
                )
                return JSONResponse(result)

        except UnknownModelError as e:
            latency_ms = int((time.time() - start_time) * 1000)
            await store.record(
                virtual_model=virtual_model,
                status="error",
                error_type="unknown_model",
                error_message=str(e),
                latency_ms=latency_ms,
                request_body=body,
            )
            return JSONResponse(
                {
                    "error": {
                        "type": "invalid_request_error",
                        "message": str(e),
                    }
                },
                status_code=400,
            )

        except AllProvidersFailedError as e:
            latency_ms = int((time.time() - start_time) * 1000)
            failover = [
                {
                    "provider": err["provider"],
                    "model": err["model"],
                    "error": err["error"],
                }
                for err in e.errors
            ]
            await store.record(
                virtual_model=virtual_model,
                status="error",
                error_type="all_providers_failed",
                error_message=str(e),
                latency_ms=latency_ms,
                request_body=body,
                failover_details=failover,
            )
            return JSONResponse(
                {
                    "error": {
                        "type": "api_error",
                        "message": str(e),
                    }
                },
                status_code=502,
            )

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            await store.record(
                virtual_model=virtual_model,
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
                latency_ms=latency_ms,
                request_body=body,
            )
            logger.error(
                "request.error",
                model=virtual_model,
                error=str(e),
                exc_info=True,
            )
            return JSONResponse(
                {
                    "error": {
                        "type": "api_error",
                        "message": str(e),
                    }
                },
                status_code=502,
            )

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        """请求级中间件：注入 request_id 到日志上下文，并记录结构化请求日志。"""
        request_id = _sanitize_request_id(request.headers.get("x-request-id"))
        bind_contextvars(request_id=request_id)
        start = time.time()
        try:
            response = await call_next(request)
            # 注意：对 StreamingResponse，call_next 在响应对象创建后即返回（状态码
            # 200、首字节尚未发送），故此处 duration_ms 仅度量请求 setup / 首字节前
            # 耗时，status_code 恒为 200 即便流中途出错。流式真实耗时与最终状态以
            # _stream_wrapper 内 store.record(...) 为准。
            logger.info(
                "http.request",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round((time.time() - start) * 1000),
            )
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            logger.error(
                "http.request_error",
                method=request.method,
                path=request.url.path,
                duration_ms=round((time.time() - start) * 1000),
                exc_info=True,
            )
            raise
        finally:
            # 仅解绑本中间件注入的 request_id，避免误清请求处理期间绑定的其它
            # 上下文（如 tenant / user id）；clear_contextvars 会清空全部 structlog 上下文。
            unbind_contextvars("request_id")

    return app


async def _stream_wrapper(
    stream, *, outcome, store, virtual_model, request_body, start_time, request_id
):
    """包装流式响应，在流完成后记录调用数据，同时从 SSE 提取 usage.

    request_id 由端点显式传入：本 wrapper 在中间件清理 contextvars 之后才被
    ASGI 消费，需在此重新绑定，使 routing 层（route_stream 函数体在首次
    async for 时才执行）的日志与 http.request 共用同一 request_id。
    """
    buffer = b""
    usage: dict = {}
    got_msg_start = False
    got_msg_delta = False

    if request_id is not None:
        bind_contextvars(request_id=request_id)
    try:
        async for chunk in stream:
            yield chunk
            buffer += chunk
            # 限制 buffer 大小，只保留最近 32KB
            if len(buffer) > 32768:
                buffer = buffer[-16384:]
            # 从 message_start 提取 input_tokens / cache
            if not got_msg_start:
                m = _SSE_MSG_START_RE.search(buffer)
                if m:
                    try:
                        data = json.loads(m.group(1))
                        usage.update(data.get("message", {}).get("usage", {}))
                        got_msg_start = True
                    except (json.JSONDecodeError, TypeError):
                        pass
            # 从 message_delta 提取 output_tokens
            if not got_msg_delta:
                m = _SSE_MSG_DELTA_RE.search(buffer)
                if m:
                    try:
                        data = json.loads(m.group(1))
                        usage.update(data.get("usage", {}))
                        got_msg_delta = True
                    except (json.JSONDecodeError, TypeError):
                        pass

        # 流成功完成
        latency_ms = int((time.time() - start_time) * 1000)
        await store.record(
            virtual_model=virtual_model,
            status="success",
            provider_name=outcome.get("provider_name"),
            provider_type=outcome.get("provider_type"),
            provider_model=outcome.get("provider_model"),
            provider_url=outcome.get("provider_url"),
            attempt=outcome.get("attempt", 1),
            latency_ms=latency_ms,
            request_body=request_body,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            cache_read_tokens=usage.get("cache_read_input_tokens"),
            cache_write_tokens=usage.get("cache_creation_input_tokens"),
            failover_details=outcome.get("_failures"),
        )
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        failover = None
        if isinstance(e, AllProvidersFailedError):
            failover = [
                {
                    "provider": err["provider"],
                    "model": err["model"],
                    "error": err["error"],
                }
                for err in e.errors
            ]
        await store.record(
            virtual_model=virtual_model,
            status="error",
            error_type=type(e).__name__,
            error_message=str(e),
            latency_ms=latency_ms,
            request_body=request_body,
            failover_details=failover,
        )
        error_body = json.dumps(
            {
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": str(e),
                },
            }
        )
        yield f"event: error\ndata: {error_body}\n\n".encode()
    finally:
        # 解绑本 wrapper 绑定的 request_id，保持上下文对称清理。
        if request_id is not None:
            unbind_contextvars("request_id")
