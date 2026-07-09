from __future__ import annotations

import json

import httpx
import pytest
from agent_router.config import (
    AppConfig,
    ProviderConfig,
    RouterConfig,
    ServerConfig,
    VirtualModelConfig,
)
from agent_router.routing import (
    Router,
    UnknownModelError,
    AllProvidersFailedError,
    _check_stream_error,
)
from agent_router.providers.base import NonRetryableError, RetryableError


class TestRouterModelLookup:
    async def test_known_model(self, sample_config, http_client):
        router = Router(sample_config, http_client)
        providers = await router._get_providers("haiku-router")
        assert len(providers) == 2
        assert providers[0].model == "claude-haiku-4-5-20251001"

    async def test_unknown_model(self, sample_config, http_client):
        router = Router(sample_config, http_client)
        with pytest.raises(UnknownModelError) as exc:
            await router._get_providers("nonexistent-router")
        assert "nonexistent-router" in str(exc.value)
        assert "haiku-router" in exc.value.known

    async def test_model_names(self, sample_config, http_client):
        router = Router(sample_config, http_client)
        names = router.model_names
        assert "haiku-router" in names
        assert "sonnet-router" in names

    async def test_unresolved_api_key_provider_is_skipped(self, http_client):
        config = AppConfig(
            server=ServerConfig(),
            models={
                "m": VirtualModelConfig(
                    providers=[
                        ProviderConfig(
                            type="anthropic",
                            name="missing",
                            model="m1",
                            api_key="${MISSING_KEY}",
                            base_url="https://missing.test",
                            priority=1,
                        ),
                        ProviderConfig(
                            type="anthropic",
                            name="ready",
                            model="m2",
                            api_key="sk-ready",
                            base_url="https://ready.test",
                            priority=2,
                        ),
                    ]
                )
            },
        )
        router = Router(config, http_client)

        providers = await router._get_providers("m")

        assert [p.name for p in providers] == ["ready"]

    async def test_all_unresolved_api_keys_fail_with_clear_error(self, http_client):
        config = AppConfig(
            server=ServerConfig(),
            models={
                "m": VirtualModelConfig(
                    providers=[
                        ProviderConfig(
                            type="anthropic",
                            name="missing",
                            model="m1",
                            api_key="${MISSING_KEY}",
                            base_url="https://missing.test",
                            priority=1,
                        ),
                    ]
                )
            },
        )
        router = Router(config, http_client)

        with pytest.raises(AllProvidersFailedError) as exc:
            await router._get_providers("m")

        assert "api_key 环境变量未设置或未正确插值" in str(exc.value)


class TestAllProvidersFailedError:
    def test_formatting(self):
        errors = [
            {"provider": "anthropic", "model": "m1", "error": "HTTP 429"},
            {"provider": "anthropic", "model": "m2", "error": "timeout"},
        ]
        exc = AllProvidersFailedError("test-model", errors)
        msg = str(exc)
        assert "test-model" in msg
        assert "HTTP 429" in msg
        assert "timeout" in msg


def _sse_error_buffer(error_type: str, message: str) -> bytes:
    """Helper to build an SSE error event buffer."""
    data = json.dumps(
        {"type": "error", "error": {"type": error_type, "message": message}}
    )
    return f"event: error\ndata: {data}\n\n".encode()


class TestCheckStreamError:
    def test_no_error_event(self):
        """Normal SSE data should not raise."""
        buf = b'event: message_start\ndata: {"message": {}}\n\n'
        _check_stream_error(buf)  # should not raise

    def test_auth_error_raises_retryable_with_immediate_break(self):
        """Auth errors should raise RetryableError with immediate_break=True."""
        buf = _sse_error_buffer("authentication_error", "Invalid API key")
        with pytest.raises(RetryableError, match="authentication_error") as exc_info:
            _check_stream_error(buf)
        assert exc_info.value.immediate_break is True

    def test_permission_error_raises_retryable_with_immediate_break(self):
        buf = _sse_error_buffer("permission_error", "Access denied")
        with pytest.raises(RetryableError, match="permission_error") as exc_info:
            _check_stream_error(buf)
        assert exc_info.value.immediate_break is True

    def test_rate_limit_error_raises_retryable(self):
        buf = _sse_error_buffer("rate_limit_error", "Too many requests")
        with pytest.raises(RetryableError, match="rate_limit_error") as exc_info:
            _check_stream_error(buf)
        assert exc_info.value.immediate_break is False
        assert exc_info.value.rate_limited is True

    def test_overloaded_error_raises_retryable(self):
        buf = _sse_error_buffer("overloaded_error", "Server busy")
        with pytest.raises(RetryableError, match="overloaded_error") as exc_info:
            _check_stream_error(buf)
        assert exc_info.value.rate_limited is True

    def test_unknown_error_type_raises_non_retryable(self):
        """Unknown error types should raise NonRetryableError."""
        buf = _sse_error_buffer("some_new_error", "Something weird")
        with pytest.raises(NonRetryableError, match="some_new_error"):
            _check_stream_error(buf)

    def test_malformed_json_raises_non_retryable(self):
        """Malformed JSON in error event should raise NonRetryableError."""
        buf = b"event: error\ndata: {broken json}\n\n"
        with pytest.raises(NonRetryableError, match="Stream error"):
            _check_stream_error(buf)

    def test_partial_buffer_no_match(self):
        """Incomplete SSE event should not raise."""
        buf = b'event: error\ndata: {"type":'
        _check_stream_error(buf)  # should not raise

    def test_error_in_later_chunk(self):
        """Error event appearing after normal data should still be detected."""
        buf = (
            b'event: message_start\ndata: {"message": {}}\n\n'
            b'event: error\ndata: {"type": "error", "error": {"type": "api_error", "message": "fail"}}\n\n'
        )
        with pytest.raises(RetryableError, match="api_error"):
            _check_stream_error(buf)


class TestRateLimitRouting:
    async def test_rate_limit_does_not_trip_circuit(self, http_client):
        """429 进入短冷却，不计入熔断连续失败."""
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(
                    429, text="rate limited", headers={"Retry-After": "60"}
                )
            return httpx.Response(
                200,
                json={
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "ok"}],
                    "model": "m2",
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            config = AppConfig(
                server=ServerConfig(),
                models={
                    "m": VirtualModelConfig(
                        providers=[
                            ProviderConfig(
                                type="anthropic",
                                name="p1",
                                model="m1",
                                api_key="k1",
                                base_url="https://p1.test",
                                priority=1,
                                failure_threshold=1,
                            ),
                            ProviderConfig(
                                type="anthropic",
                                name="p2",
                                model="m2",
                                api_key="k2",
                                base_url="https://p2.test",
                                priority=2,
                            ),
                        ]
                    )
                },
            )
            router = Router(config, client)
            result = await router.route_non_stream(
                {"model": "m", "max_tokens": 10, "messages": []}
            )
            assert result["model"] == "m2"
            # p1 未熔断
            from agent_router.circuit_breaker import CircuitState

            assert (await router.circuit_breaker.state("p1")) == CircuitState.CLOSED
            assert router.provider_gate.is_in_cooldown("p1")

    async def test_sticky_does_not_failover(self, http_client):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            config = AppConfig(
                server=ServerConfig(),
                router=RouterConfig(mode="sticky"),
                models={
                    "m": VirtualModelConfig(
                        pinned_provider="p1",
                        pinned_model="m1",
                        providers=[
                            ProviderConfig(
                                type="anthropic",
                                name="p1",
                                model="m1",
                                api_key="k1",
                                base_url="https://p1.test",
                                priority=1,
                            ),
                            ProviderConfig(
                                type="anthropic",
                                name="p2",
                                model="m2",
                                api_key="k2",
                                base_url="https://p2.test",
                                priority=2,
                            ),
                        ],
                    )
                },
            )
            router = Router(config, client)
            with pytest.raises(AllProvidersFailedError) as exc:
                await router.route_non_stream(
                    {"model": "m", "max_tokens": 10, "messages": []}
                )
            assert len(exc.value.errors) == 1
            assert exc.value.errors[0]["provider"] == "p1"

    async def test_sticky_rate_limit_raises_no_provider(self, http_client):
        from agent_router.routing import NoProviderAvailableError

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, text="rl", headers={"Retry-After": "9"})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            config = AppConfig(
                server=ServerConfig(),
                router=RouterConfig(mode="sticky"),
                models={
                    "m": VirtualModelConfig(
                        pinned_provider="p1",
                        pinned_model="m1",
                        providers=[
                            ProviderConfig(
                                type="anthropic",
                                name="p1",
                                model="m1",
                                api_key="k1",
                                base_url="https://p1.test",
                                priority=1,
                            ),
                        ],
                    )
                },
            )
            router = Router(config, client)
            with pytest.raises(NoProviderAvailableError) as exc:
                await router.route_non_stream(
                    {"model": "m", "max_tokens": 10, "messages": []}
                )
            assert exc.value.kind == "rate_limit"
            assert exc.value.retry_after == 9.0
