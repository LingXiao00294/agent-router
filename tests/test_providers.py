from __future__ import annotations

import json

import httpx
import pytest
from agent_router.config import ProviderConfig
from agent_router.providers.anthropic_compat import AnthropicCompatProvider
from agent_router.providers.base import NonRetryableError, RetryableError


@pytest.fixture
def provider(http_client):
    config = ProviderConfig(
        type="anthropic",
        model="claude-haiku-4-5-20251001",
        api_key="sk-ant-test-key",
        base_url="https://api.anthropic.com",
        priority=1,
    )
    return AnthropicCompatProvider(config, http_client)


class TestAnthropicCompatProvider:
    def test_prepare_body_replaces_model(self, provider):
        body = {
            "model": "haiku-router",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": "hello"}],
        }
        result = provider._prepare_body(body)
        assert result["model"] == "claude-haiku-4-5-20251001"
        assert result["max_tokens"] == 100
        assert result["messages"] == body["messages"]

    def test_prepare_body_does_not_mutate_original(self, provider):
        body = {"model": "original", "max_tokens": 100, "messages": []}
        provider._prepare_body(body)
        assert body["model"] == "original"

    def test_build_headers_with_anthropic_key(self, provider):
        body = {}
        headers = provider._build_headers(body)
        assert headers["x-api-key"] == "sk-ant-test-key"
        assert headers["Content-Type"] == "application/json"

    def test_build_headers_with_bearer_key(self, http_client):
        config = ProviderConfig(
            type="anthropic",
            model="test",
            api_key="not-anthropic-key-format",
            base_url="https://test.com",
            priority=1,
        )
        provider = AnthropicCompatProvider(config, http_client)
        headers = provider._build_headers({})
        assert headers["Authorization"] == "Bearer not-anthropic-key-format"

    @pytest.mark.asyncio
    async def test_send_retryable_429(self, http_client):
        """测试 HTTP 429 触发可重试错误."""
        config = ProviderConfig(
            type="anthropic",
            model="test",
            api_key="sk-test",
            base_url="https://httpstat.us",
            priority=1,
        )
        provider = AnthropicCompatProvider(config, http_client)
        with pytest.raises(RetryableError):
            await provider.send({"model": "test", "max_tokens": 10, "messages": []})

    @pytest.mark.asyncio
    async def test_send_retryable_401(self, http_client):
        """测试 HTTP 401 (鉴权失败) 触发可重试错误，允许路由切换 provider."""
        config = ProviderConfig(
            type="anthropic",
            model="test",
            api_key="invalid",
            base_url="https://api.anthropic.com",
            priority=1,
        )
        provider = AnthropicCompatProvider(config, http_client)
        with pytest.raises(RetryableError):
            await provider.send({"model": "test", "max_tokens": 10, "messages": []})

    def test_strip_trailing_slash(self):
        config = ProviderConfig(
            type="anthropic",
            model="test",
            api_key="k",
            base_url="https://api.com/",
            priority=1,
        )
        assert config.base_url == "https://api.com"
