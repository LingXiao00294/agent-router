from __future__ import annotations

import asyncio

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from agent_router.app import (
    _calculate_cost_usd,
    _close_prefetched_stream,
    _prefetch_first_chunk,
    _stream_wrapper,
    create_app,
)
from agent_router.config import (
    AppConfig,
    ModelRef,
    ProviderConfig,
    RouterConfig,
    ServerConfig,
    VirtualModelConfig,
    parse_config_data,
)
from agent_router.db import CallStore
from agent_router.routing import Router


class TestCostCalculation:
    def test_calculates_all_token_categories(self):
        usage = {
            "input_tokens": 1_000_000,
            "output_tokens": 500_000,
            "cache_read_input_tokens": 2_000_000,
            "cache_creation_input_tokens": 250_000,
        }
        outcome = {
            "pricing": {
                "input": 1.0,
                "output": 4.0,
                "cache_read": 0.1,
                "cache_write": 1.2,
            }
        }

        assert _calculate_cost_usd(usage, outcome) == 3.5

    def test_missing_pricing_is_free(self):
        assert _calculate_cost_usd({"input_tokens": 1_000_000}, {}) == 0.0

    @pytest.mark.asyncio
    async def test_streaming_route_persists_calculated_cost(self, store):
        """Persist streamed usage cost with the selected provider prices."""
        sse = (
            b"event: message_start\n"
            b'data: {"message":{"usage":{"input_tokens":100,'
            b'"cache_read_input_tokens":200,"cache_creation_input_tokens":50}}}\n\n'
            b"event: message_delta\n"
            b'data: {"usage":{"output_tokens":25}}\n\n'
            b"event: message_stop\n"
            b"data: {}\n\n"
        )
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, content=sse)
        )
        http_client = httpx.AsyncClient(transport=transport)
        config = parse_config_data(
            {
                "router": {"mode": "failover"},
                "providers": {
                    "provider": {
                        "type": "anthropic",
                        "api_key": "test-key",
                        "base_url": "https://provider.test",
                        "models": {
                            "real-model": {
                                "input_price_per_million": 2.0,
                                "output_price_per_million": 8.0,
                                "cache_read_price_per_million": 0.2,
                                "cache_write_price_per_million": 3.0,
                            }
                        },
                    }
                },
                "models": {
                    "priced": {
                        "models": [{"provider": "provider", "model": "real-model"}]
                    }
                },
            }
        )
        router = Router(config, http_client)
        outcome: dict = {}
        body = {
            "model": "priced",
            "stream": True,
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "hi"}],
        }

        try:
            async for _ in _stream_wrapper(
                router.route_stream(body, outcome),
                outcome=outcome,
                store=store,
                virtual_model="priced",
                request_body=body,
                start_time=0.0,
                request_id="stream-cost-test",
            ):
                pass
        finally:
            await http_client.aclose()

        calls, total = await store.list_calls()
        assert total == 1
        assert calls[0]["input_tokens"] == 100
        assert calls[0]["output_tokens"] == 25
        assert calls[0]["cache_read_tokens"] == 200
        assert calls[0]["cache_write_tokens"] == 50
        assert calls[0]["input_price_per_million"] == 2.0
        assert calls[0]["output_price_per_million"] == 8.0
        assert calls[0]["cache_read_price_per_million"] == 0.2
        assert calls[0]["cache_write_price_per_million"] == 3.0
        assert calls[0]["cost_usd"] == pytest.approx(0.00059)

    @pytest.mark.parametrize("configured_price", [None, 0.0])
    async def test_non_stream_preserves_missing_and_zero_prices(
        self, store, configured_price
    ):
        response = {
            "id": "msg_1",
            "type": "message",
            "model": "real-model",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_input_tokens": 25,
                "cache_creation_input_tokens": 10,
            },
        }
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json=response)
        )
        config = AppConfig(
            server=ServerConfig(),
            router=RouterConfig(mode="failover"),
            models={
                "priced": VirtualModelConfig(
                    providers=[
                        ProviderConfig(
                            type="anthropic",
                            name="provider",
                            model="real-model",
                            api_key="test-key",
                            base_url="https://provider.test",
                            priority=1,
                            input_price_per_million=configured_price,
                            output_price_per_million=configured_price,
                            cache_read_price_per_million=configured_price,
                            cache_write_price_per_million=configured_price,
                        )
                    ]
                )
            },
        )
        body = {
            "model": "priced",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "hi"}],
        }

        async with httpx.AsyncClient(transport=transport) as upstream:
            app = create_app(config, store)
            app.state.router_engine = Router(config, upstream)
            asgi = ASGITransport(app=app)
            async with AsyncClient(transport=asgi, base_url="http://test") as client:
                api_response = await client.post("/v1/messages", json=body)

        assert api_response.status_code == 200
        calls, total = await store.list_calls()
        assert total == 1
        for column in (
            "input_price_per_million",
            "output_price_per_million",
            "cache_read_price_per_million",
            "cache_write_price_per_million",
        ):
            assert calls[0][column] == configured_price
        assert calls[0]["cost_usd"] == 0.0

    async def test_non_stream_failover_persists_final_provider_prices(self, store):
        usage = {
            "input_tokens": 1_000_000,
            "output_tokens": 500_000,
            "cache_read_input_tokens": 2_000_000,
            "cache_creation_input_tokens": 250_000,
        }

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "first.test":
                return httpx.Response(500, text="first failed")
            return httpx.Response(
                200,
                json={"id": "msg_2", "model": "shared-model", "usage": usage},
            )

        transport = httpx.MockTransport(handler)
        config = AppConfig(
            server=ServerConfig(),
            router=RouterConfig(mode="failover"),
            models={
                "router": VirtualModelConfig(
                    providers=[
                        ProviderConfig(
                            type="anthropic",
                            name="first",
                            model="shared-model",
                            api_key="first-key",
                            base_url="https://first.test",
                            priority=1,
                            input_price_per_million=90.0,
                            output_price_per_million=90.0,
                            cache_read_price_per_million=90.0,
                            cache_write_price_per_million=90.0,
                        ),
                        ProviderConfig(
                            type="anthropic",
                            name="second",
                            model="shared-model",
                            api_key="second-key",
                            base_url="https://second.test",
                            priority=2,
                            input_price_per_million=1.0,
                            output_price_per_million=4.0,
                            cache_read_price_per_million=0.1,
                            cache_write_price_per_million=1.2,
                        ),
                    ]
                )
            },
        )
        body = {"model": "router", "max_tokens": 100, "messages": []}

        async with httpx.AsyncClient(transport=transport) as upstream:
            app = create_app(config, store)
            app.state.router_engine = Router(config, upstream)
            asgi = ASGITransport(app=app)
            async with AsyncClient(transport=asgi, base_url="http://test") as client:
                response = await client.post("/v1/messages", json=body)

        assert response.status_code == 200
        calls, total = await store.list_calls()
        assert total == 1
        call = calls[0]
        assert call["provider_name"] == "second"
        assert call["provider_model"] == "shared-model"
        assert call["attempt"] == 2
        assert call["input_price_per_million"] == 1.0
        assert call["output_price_per_million"] == 4.0
        assert call["cache_read_price_per_million"] == 0.1
        assert call["cache_write_price_per_million"] == 1.2
        assert call["cost_usd"] == 3.5

    async def test_stream_failover_persists_final_provider_prices(self, store):
        first_error = (
            b'event: error\ndata: {"type":"error","error":'
            b'{"type":"api_error","message":"first failed"}}\n\n'
        )
        success = (
            b"event: message_start\n"
            b'data: {"message":{"usage":{"input_tokens":100,'
            b'"cache_read_input_tokens":200,"cache_creation_input_tokens":50}}}\n\n'
            b"event: message_delta\n"
            b'data: {"usage":{"output_tokens":25}}\n\n'
            b"event: message_stop\ndata: {}\n\n"
        )

        def handler(request: httpx.Request) -> httpx.Response:
            content = first_error if request.url.host == "first.test" else success
            return httpx.Response(200, content=content)

        transport = httpx.MockTransport(handler)
        config = AppConfig(
            server=ServerConfig(),
            router=RouterConfig(mode="failover"),
            models={
                "router": VirtualModelConfig(
                    providers=[
                        ProviderConfig(
                            type="anthropic",
                            name="first",
                            model="shared-model",
                            api_key="first-key",
                            base_url="https://first.test",
                            priority=1,
                            input_price_per_million=90.0,
                            output_price_per_million=90.0,
                            cache_read_price_per_million=90.0,
                            cache_write_price_per_million=90.0,
                        ),
                        ProviderConfig(
                            type="anthropic",
                            name="second",
                            model="shared-model",
                            api_key="second-key",
                            base_url="https://second.test",
                            priority=2,
                            input_price_per_million=2.0,
                            output_price_per_million=8.0,
                            cache_read_price_per_million=0.2,
                            cache_write_price_per_million=3.0,
                        ),
                    ]
                )
            },
        )
        body = {
            "model": "router",
            "stream": True,
            "max_tokens": 100,
            "messages": [],
        }

        async with httpx.AsyncClient(transport=transport) as upstream:
            router = Router(config, upstream)
            outcome: dict = {}
            chunks = [
                chunk
                async for chunk in _stream_wrapper(
                    router.route_stream(body, outcome),
                    outcome=outcome,
                    store=store,
                    virtual_model="router",
                    request_body=body,
                    start_time=0.0,
                    request_id="stream-failover-price-test",
                )
            ]

        assert b"event: error" not in b"".join(chunks)
        calls, total = await store.list_calls()
        assert total == 1
        call = calls[0]
        assert call["provider_name"] == "second"
        assert call["provider_model"] == "shared-model"
        assert call["attempt"] == 2
        assert call["input_price_per_million"] == 2.0
        assert call["output_price_per_million"] == 8.0
        assert call["cache_read_price_per_million"] == 0.2
        assert call["cache_write_price_per_million"] == 3.0
        assert call["cost_usd"] == pytest.approx(0.00059)

    async def test_failed_call_has_null_price_snapshots(self, store):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(500, text="upstream failed")
        )
        config = AppConfig(
            server=ServerConfig(),
            router=RouterConfig(mode="failover"),
            models={
                "router": VirtualModelConfig(
                    providers=[
                        ProviderConfig(
                            type="anthropic",
                            name="provider",
                            model="real-model",
                            api_key="test-key",
                            base_url="https://provider.test",
                            priority=1,
                            input_price_per_million=1.0,
                            output_price_per_million=4.0,
                            cache_read_price_per_million=0.1,
                            cache_write_price_per_million=1.2,
                        )
                    ]
                )
            },
        )
        body = {"model": "router", "max_tokens": 100, "messages": []}

        async with httpx.AsyncClient(transport=transport) as upstream:
            app = create_app(config, store)
            app.state.router_engine = Router(config, upstream)
            asgi = ASGITransport(app=app)
            async with AsyncClient(transport=asgi, base_url="http://test") as client:
                response = await client.post("/v1/messages", json=body)

        assert response.status_code == 502
        calls, total = await store.list_calls()
        assert total == 1
        call = calls[0]
        assert call["provider_name"] is None
        assert call["provider_model"] is None
        assert call["input_price_per_million"] is None
        assert call["output_price_per_million"] is None
        assert call["cache_read_price_per_million"] is None
        assert call["cache_write_price_per_million"] is None
        assert call["cost_usd"] is None


class TestPrefetchHelpers:
    async def test_prefetch_timeout_returns_pending_task(self):
        async def slow():
            await asyncio.sleep(1.0)
            yield b"data"

        agen = slow()
        first, pending = await _prefetch_first_chunk(agen, timeout=0.05)
        assert first is None
        assert pending is not None
        assert not pending.done()
        await _close_prefetched_stream(agen, pending)
        assert pending.done()

    async def test_prefetch_completes_within_timeout(self):
        async def fast():
            yield b"hello"

        agen = fast()
        first, pending = await _prefetch_first_chunk(agen, timeout=1.0)
        assert first == b"hello"
        assert pending is None
        await _close_prefetched_stream(agen, None)

    async def test_close_waits_for_cancel_before_aclose(self):
        """cancel 后必须等 task 结束再 aclose，避免 generator already running."""
        entered = asyncio.Event()

        async def blocked():
            entered.set()
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                await asyncio.sleep(0)  # 让出一拍，模拟清理
                raise
            yield b"x"  # pragma: no cover

        agen = blocked()
        task = asyncio.create_task(anext(agen))
        await entered.wait()
        # 不应抛 RuntimeError
        await _close_prefetched_stream(agen, task)
        assert task.done()


@pytest.fixture
def app_config():
    return AppConfig(
        server=ServerConfig(host="127.0.0.1", port=9456),
        models={
            "test-router": VirtualModelConfig(
                providers=[
                    ProviderConfig(
                        type="anthropic",
                        name="anthropic",
                        model="claude-haiku-4-5-20251001",
                        api_key="sk-ant-test",
                        base_url="https://api.anthropic.com",
                        priority=1,
                    ),
                ]
            ),
        },
    )


@pytest.fixture
async def store():
    s = CallStore(":memory:")
    await s.init()
    yield s
    await s.close()


@pytest.fixture
async def client(app_config, store):
    app = create_app(app_config, store)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestHealth:
    @pytest.mark.asyncio
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestModels:
    @pytest.mark.asyncio
    async def test_list_models(self, client):
        resp = await client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert len(data["data"]) == 1
        assert data["data"][0]["id"] == "test-router"


class TestMessages:
    @pytest.mark.asyncio
    async def test_unknown_model(self, client):
        resp = await client.post(
            "/v1/messages",
            json={
                "model": "nonexistent",
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data

    @pytest.mark.asyncio
    async def test_non_stream_request(self, client):
        """非流式请求: 会尝试真实调用 Anthropic API, 预期鉴权失败 (401)."""
        resp = await client.post(
            "/v1/messages",
            json={
                "model": "test-router",
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
        # 预期 502 因为 api key 是假的, 或者 401 从上游透传
        assert resp.status_code in (401, 502)

    @pytest.mark.asyncio
    async def test_stream_rate_limit_returns_http_429(self, store):
        """流式在首字节前限流时返回 HTTP 429 + Retry-After，而非 SSE 内嵌错误."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, text="rl", headers={"Retry-After": "7"})

        transport = httpx.MockTransport(handler)
        http_client = httpx.AsyncClient(transport=transport)
        config = AppConfig(
            server=ServerConfig(),
            router=RouterConfig(mode="sticky"),
            models={
                "m": VirtualModelConfig(
                    pinned_model=ModelRef(provider="p1", model="m1"),
                    providers=[
                        ProviderConfig(
                            type="anthropic",
                            name="p1",
                            model="m1",
                            api_key="k",
                            base_url="https://p1.test",
                            priority=1,
                        )
                    ],
                )
            },
        )
        app = create_app(config, store)
        # 注入带 mock transport 的 router
        app.state.router_engine = Router(config, http_client)

        asgi = ASGITransport(app=app)
        async with AsyncClient(transport=asgi, base_url="http://test") as ac:
            resp = await ac.post(
                "/v1/messages",
                json={
                    "model": "m",
                    "stream": True,
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
        await http_client.aclose()
        assert resp.status_code == 429
        assert resp.headers.get("retry-after") in {"7", "6"}  # ceil of remaining
        assert int(resp.headers.get("retry-after", "0")) >= 6
        assert resp.json()["error"]["type"] == "rate_limit_error"

    @pytest.mark.asyncio
    async def test_stream_prefetch_timeout_still_returns_sse(self, store, monkeypatch):
        """首字节预取超时后仍应先返回 SSE 头，再在响应体中交付内容."""
        import agent_router.app as app_mod

        # 调用时读取模块常量，monkeypatch 可生效
        monkeypatch.setattr(app_mod, "_STREAM_FIRST_BYTE_PREFETCH_TIMEOUT", 0.05)

        async def slow_body():
            await asyncio.sleep(0.2)
            yield b'event: message_start\ndata: {"type":"message_start"}\n\n'

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=slow_body())

        transport = httpx.MockTransport(handler)
        http_client = httpx.AsyncClient(transport=transport)
        config = AppConfig(
            server=ServerConfig(),
            router=RouterConfig(mode="failover"),
            models={
                "m": VirtualModelConfig(
                    providers=[
                        ProviderConfig(
                            type="anthropic",
                            name="p1",
                            model="m1",
                            api_key="k",
                            base_url="https://p1.test",
                            priority=1,
                        )
                    ],
                )
            },
        )
        app = create_app(config, store)
        app.state.router_engine = Router(config, http_client)

        asgi = ASGITransport(app=app)
        async with AsyncClient(transport=asgi, base_url="http://test") as ac:
            resp = await ac.post(
                "/v1/messages",
                json={
                    "model": "m",
                    "stream": True,
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
        await http_client.aclose()
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        assert b"message_start" in resp.content


class TestRecordCall:
    @pytest.mark.asyncio
    async def test_record_and_retrieve(self, store):
        call_id = await store.record(
            virtual_model="test-router",
            status="success",
            provider_type="anthropic",
            provider_model="claude-test",
            latency_ms=500,
            input_tokens=100,
            output_tokens=50,
        )
        assert call_id is not None

        call = await store.get_call(call_id)
        assert call is not None
        assert call["virtual_model"] == "test-router"
        assert call["status"] == "success"
        assert call["input_tokens"] == 100

    @pytest.mark.asyncio
    async def test_summary(self, store):
        await store.record(
            virtual_model="test",
            status="success",
            input_tokens=100,
            output_tokens=50,
        )
        await store.record(
            virtual_model="test",
            status="error",
            error_type="timeout",
            error_message="timeout",
        )
        summary = await store.summary()
        assert summary["total_calls"] == 2
        assert summary["success_count"] == 1
        assert summary["error_count"] == 1
        assert summary["success_rate"] == 50.0
        assert summary["total_input_tokens"] == 100
        assert summary["total_output_tokens"] == 50

    @pytest.mark.asyncio
    async def test_daily_trend_includes_token_details_and_cost(self, store):
        await store.record(
            virtual_model="test",
            status="success",
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=300,
            cache_write_tokens=25,
            cost_usd=0.0125,
        )

        rows = await store.daily_trend(days=1)

        assert len(rows) == 1
        assert rows[0]["input_tokens"] == 100
        assert rows[0]["output_tokens"] == 50
        assert rows[0]["cache_read_tokens"] == 300
        assert rows[0]["cache_write_tokens"] == 25
        assert rows[0]["cost_usd"] == 0.0125

    @pytest.mark.asyncio
    async def test_list_calls_pagination(self, store):
        for i in range(5):
            await store.record(
                virtual_model="test",
                status="success",
            )
        calls, total = await store.list_calls(page=1, size=3)
        assert len(calls) == 3
        assert total == 5

    @pytest.mark.asyncio
    async def test_list_calls_status_filter(self, store):
        await store.record(virtual_model="m", status="success")
        await store.record(
            virtual_model="m",
            status="error",
            error_type="timeout",
            error_message="boom",
        )
        await store.record(virtual_model="m", status="success")

        calls, total = await store.list_calls(status="error")
        assert total == 1
        assert all(c["status"] == "error" for c in calls)

        calls, total = await store.list_calls(status="success")
        assert total == 2
        assert all(c["status"] == "success" for c in calls)

    @pytest.mark.asyncio
    async def test_list_calls_model_status_combo(self, store):
        await store.record(virtual_model="a", status="success")
        await store.record(
            virtual_model="a",
            status="error",
            error_type="x",
            error_message="y",
        )
        await store.record(
            virtual_model="b",
            status="error",
            error_type="x",
            error_message="y",
        )

        calls, total = await store.list_calls(model="a", status="error")
        assert total == 1
        assert all(c["virtual_model"] == "a" and c["status"] == "error" for c in calls)

        # 单独 model 过滤仍正常工作
        _, total = await store.list_calls(model="b")
        assert total == 1

    async def test_real_model_metrics_group_by_provider_and_model(self, store, client):
        await store.record(
            virtual_model="router-a",
            status="success",
            provider_name="provider-a",
            provider_model="shared-model",
            input_tokens=100,
        )
        await store.record(
            virtual_model="router-b",
            status="success",
            provider_name="provider-b",
            provider_model="shared-model",
            input_tokens=200,
        )

        response = await client.get("/api/metrics/by-real-model")

        assert response.status_code == 200
        rows = response.json()
        assert {
            (row["provider"], row["model"], row["total_input_tokens"]) for row in rows
        } == {
            ("provider-a", "shared-model", 100),
            ("provider-b", "shared-model", 200),
        }
        assert all("display_name" not in row for row in rows)

    async def test_list_calls_filters_by_structured_actual_model(self, store):
        await store.record(
            virtual_model="router",
            status="success",
            provider_name="provider-a",
            provider_model="shared-model",
        )
        await store.record(
            virtual_model="router",
            status="success",
            provider_name="provider-b",
            provider_model="shared-model",
        )

        calls, total = await store.list_calls(
            provider="provider-b", provider_model="shared-model"
        )

        assert total == 1
        assert calls[0]["provider_name"] == "provider-b"
