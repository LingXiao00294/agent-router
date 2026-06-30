from __future__ import annotations

import pytest
import httpx
from httpx import ASGITransport, AsyncClient

from agent_router.dashboard import create_dashboard_app, find_dashboard_dist


def _create_dist(tmp_path):
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text(
        '<html><script type="module" src="/assets/app.js"></script></html>',
        encoding="utf-8",
    )
    (assets / "app.js").write_text("console.log('ok')", encoding="utf-8")
    return dist


def test_find_dashboard_dist_accepts_explicit_path(tmp_path):
    dist = _create_dist(tmp_path)

    assert find_dashboard_dist(dist) == dist.resolve()


@pytest.mark.asyncio
async def test_dashboard_serves_spa_and_assets(tmp_path):
    dist = _create_dist(tmp_path)
    app = create_dashboard_app(dist)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        index = await client.get("/")
        nested = await client.get("/config/providers")
        asset = await client.get("/assets/app.js")

    assert index.status_code == 200
    assert "/assets/app.js" in index.text
    assert nested.status_code == 200
    assert "/assets/app.js" in nested.text
    assert asset.status_code == 200
    assert "console.log" in asset.text


@pytest.mark.asyncio
async def test_dashboard_proxies_router_api(tmp_path, httpx_mock):
    dist = _create_dist(tmp_path)
    httpx_mock.add_response(
        method="GET",
        url="http://router.local/api/metrics/summary",
        json={"total_calls": 0},
    )
    app = create_dashboard_app(dist, router_base_url="http://router.local")
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/metrics/summary")

    assert response.status_code == 200
    assert response.json() == {"total_calls": 0}


@pytest.mark.asyncio
async def test_dashboard_returns_502_when_router_is_unavailable(tmp_path, httpx_mock):
    dist = _create_dist(tmp_path)
    httpx_mock.add_exception(
        httpx.ConnectError("connection refused"),
        method="GET",
        url="http://router.local/api/metrics/summary",
    )
    app = create_dashboard_app(dist, router_base_url="http://router.local")
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/metrics/summary")

    assert response.status_code == 502
    assert "无法连接到 router API" in response.json()["detail"]
