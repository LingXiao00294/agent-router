from __future__ import annotations

import json
import re
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agent_router.api.config import create_config_router
from agent_router.api.metrics import create_metrics_router
from agent_router.config import AppConfig, load_config
from agent_router.db import CallStore
from agent_router.routing import AllProvidersFailedError, Router, UnknownModelError

logger = structlog.get_logger(__name__)

# 从 SSE 流中提取 usage 的正则 (message_start 有 input_tokens, message_delta 有 output_tokens)
_SSE_MSG_START_RE = re.compile(
    rb"event:\s*message_start\s*\r?\ndata:\s*(\{.*?\})\s*(?:\r?\n|$)", re.DOTALL
)
_SSE_MSG_DELTA_RE = re.compile(
    rb"event:\s*message_delta\s*\r?\ndata:\s*(\{.*?\})\s*(?:\r?\n|$)", re.DOTALL
)


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
        await router_engine.reload_config(new_config)

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
                {"provider": err["provider"], "model": err["model"], "error": err["error"]}
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

    # 托管 dashboard 静态文件 (放在最后，避免覆盖 API 路由)
    _mount_dashboard(app)

    return app


async def _stream_wrapper(
    stream, *, outcome, store, virtual_model, request_body, start_time
):
    """包装流式响应，在流完成后记录调用数据，同时从 SSE 提取 usage."""
    buffer = b""
    usage: dict = {}
    got_msg_start = False
    got_msg_delta = False

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
                {"provider": err["provider"], "model": err["model"], "error": err["error"]}
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


def _mount_dashboard(app: FastAPI) -> None:
    """挂载 dashboard 静态文件，支持 SPA 路由."""
    dist = Path(__file__).parent.parent.parent / "dashboard" / "dist"
    if not dist.is_dir():
        dist = Path("dashboard") / "dist"  # CWD fallback for wheel installs
    if not dist.is_dir():
        return

    # 先挂载静态资源
    assets = dist / "assets"
    if assets.is_dir():
        app.mount(
            "/assets", StaticFiles(directory=str(assets)), name="dashboard_assets"
        )

    # SPA fallback: 非 API 的 GET 请求返回 index.html
    index_path = dist / "index.html"

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        from fastapi.responses import Response

        if full_path.startswith(("api/", "v1/")) or full_path == "health":
            return Response(status_code=404)
        if index_path.is_file():
            return FileResponse(str(index_path))
        return Response(status_code=404)
