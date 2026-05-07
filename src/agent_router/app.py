from __future__ import annotations

import json
import re
import time
import traceback
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from agent_router.api.config import create_config_router
from agent_router.api.metrics import create_metrics_router
from agent_router.config import AppConfig
from agent_router.db import CallStore
from agent_router.routing import AllProvidersFailedError, Router, UnknownModelError

logger = structlog.get_logger(__name__)

# 从 SSE 流中提取 usage 的正则 (message_start 有 input_tokens, message_delta 有 output_tokens)
_SSE_MSG_START_RE = re.compile(rb'event:\s*message_start\s*\ndata:\s*(\{.*\})', re.DOTALL)
_SSE_MSG_DELTA_RE = re.compile(rb'event:\s*message_delta\s*\ndata:\s*(\{.*\})', re.DOTALL)


def create_app(config: AppConfig, store: CallStore, config_path: str = "config.toml") -> FastAPI:
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
    config_router = create_config_router(config_path)
    app.include_router(config_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

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
            await store.record(
                virtual_model=virtual_model,
                status="error",
                error_type="all_providers_failed",
                error_message=str(e),
                latency_ms=latency_ms,
                request_body=body,
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
                traceback=traceback.format_exc(),
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

    return app


async def _stream_wrapper(stream, *, outcome, store, virtual_model, request_body, start_time):
    """包装流式响应，在流完成后记录调用数据，同时从 SSE 提取 usage."""
    buffer = b""
    usage: dict = {}

    try:
        async for chunk in stream:
            yield chunk
            buffer += chunk
            # 从 message_start 提取 input_tokens / cache
            m = _SSE_MSG_START_RE.search(buffer)
            if m:
                try:
                    data = json.loads(m.group(1))
                    usage.update(data.get("message", {}).get("usage", {}))
                except (json.JSONDecodeError, TypeError):
                    pass
            # 从 message_delta 提取 output_tokens
            m = _SSE_MSG_DELTA_RE.search(buffer)
            if m:
                try:
                    data = json.loads(m.group(1))
                    usage.update(data.get("usage", {}))
                except (json.JSONDecodeError, TypeError):
                    pass

        # 流成功完成
        latency_ms = int((time.time() - start_time) * 1000)
        await store.record(
            virtual_model=virtual_model,
            status="success",
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
        )
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        await store.record(
            virtual_model=virtual_model,
            status="error",
            error_type=type(e).__name__,
            error_message=str(e),
            latency_ms=latency_ms,
            request_body=request_body,
        )
        raise


