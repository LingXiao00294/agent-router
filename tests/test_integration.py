from __future__ import annotations

import pytest
from httpx import AsyncClient, ASGITransport

from agent_router.config import AppConfig, ServerConfig, ProviderConfig
from agent_router.db import CallStore
from agent_router.app import create_app


@pytest.fixture
def app_config():
    return AppConfig(
        server=ServerConfig(host="127.0.0.1", port=9456),
        models={
            "test-router": [
                ProviderConfig(
                    type="anthropic",
                    model="claude-haiku-4-5-20251001",
                    api_key="sk-ant-test",
                    base_url="https://api.anthropic.com",
                    priority=1,
                ),
            ],
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
            virtual_model="test", status="success",
            input_tokens=100, output_tokens=50,
        )
        await store.record(
            virtual_model="test", status="error",
            error_type="timeout", error_message="timeout",
        )
        summary = await store.summary()
        assert summary["total_calls"] == 2
        assert summary["success_count"] == 1
        assert summary["error_count"] == 1
        assert summary["success_rate"] == 50.0
        assert summary["total_input_tokens"] == 100
        assert summary["total_output_tokens"] == 50

    @pytest.mark.asyncio
    async def test_list_calls_pagination(self, store):
        for i in range(5):
            await store.record(
                virtual_model="test", status="success",
            )
        calls, total = await store.list_calls(page=1, size=3)
        assert len(calls) == 3
        assert total == 5
