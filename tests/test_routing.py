from __future__ import annotations

import json

import pytest
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

    def test_overloaded_error_raises_retryable(self):
        buf = _sse_error_buffer("overloaded_error", "Server busy")
        with pytest.raises(RetryableError, match="overloaded_error"):
            _check_stream_error(buf)

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
