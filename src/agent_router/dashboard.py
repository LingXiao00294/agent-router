from __future__ import annotations

import asyncio
import mimetypes
from collections.abc import Iterable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Final

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

DEFAULT_ROUTER_URL = "http://127.0.0.1:9456"

_PROXY_METHODS: Final = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
_HOP_BY_HOP_HEADERS: Final = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def find_dashboard_dist(explicit_path: str | Path | None = None) -> Path | None:
    """Return the first usable dashboard dist directory."""
    if explicit_path is not None:
        candidate = Path(explicit_path)
        if (candidate / "index.html").is_file():
            return candidate.resolve()
        return None

    package_root = Path(__file__).resolve().parent
    repo_root = package_root.parent.parent
    candidates = [
        package_root / "dashboard_dist",
        repo_root / "dashboard" / "dist",
        Path.cwd() / "dashboard" / "dist",
    ]

    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate.resolve()
    return None


def create_dashboard_app(
    dist_dir: str | Path,
    router_base_url: str = DEFAULT_ROUTER_URL,
) -> FastAPI:
    """Create the standalone dashboard app with API proxying."""
    dist = Path(dist_dir).resolve()
    index_path = dist / "index.html"
    if not index_path.is_file():
        raise ValueError(f"dashboard dist 不完整，缺少 index.html: {dist}")

    router_url = router_base_url.rstrip("/")
    http_client = httpx.AsyncClient(
        base_url=router_url,
        timeout=httpx.Timeout(60.0, connect=5.0),
        trust_env=False,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await http_client.aclose()

    app = FastAPI(
        title="Agent Router Dashboard",
        description="Agent Router 独立监控面板",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.api_route("/health", methods=_PROXY_METHODS)
    async def proxy_health(request: Request):
        return await _proxy_to_router(request, http_client)

    @app.api_route("/api/{path:path}", methods=_PROXY_METHODS)
    async def proxy_api(path: str, request: Request):
        return await _proxy_to_router(request, http_client)

    @app.api_route("/v1/{path:path}", methods=_PROXY_METHODS)
    async def proxy_v1(path: str, request: Request):
        return await _proxy_to_router(request, http_client)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if full_path.startswith(("api/", "v1/")) or full_path == "health":
            return Response(status_code=404)

        requested_file = _resolve_dist_file(dist, full_path)
        if requested_file is None:
            return _file_response(index_path)
        if requested_file.is_file():
            return _file_response(requested_file)
        return _file_response(index_path)

    return app


def _resolve_dist_file(dist: Path, request_path: str) -> Path | None:
    requested_file = (dist / request_path).resolve()
    try:
        requested_file.relative_to(dist)
    except ValueError:
        return None
    return requested_file


def _file_response(path: Path) -> Response:
    media_type, _ = mimetypes.guess_type(path.name)
    return Response(
        content=path.read_bytes(),
        media_type=media_type or "application/octet-stream",
    )


async def _proxy_to_router(
    request: Request,
    http_client: httpx.AsyncClient,
) -> Response:
    path = request.url.path
    if request.url.query:
        path = f"{path}?{request.url.query}"

    try:
        upstream = await http_client.request(
            request.method,
            path,
            content=await request.body(),
            headers=[
                *_filtered_headers(request.headers.items()),
                ("accept-encoding", "identity"),
            ],
        )
    except asyncio.CancelledError:
        return Response(status_code=499)
    except httpx.RequestError as exc:
        return JSONResponse(
            {
                "detail": (
                    "dashboard 无法连接到 router API，"
                    f"请确认 router 已启动且 --router-url 配置正确: {exc}"
                )
            },
            status_code=502,
        )
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=dict(_filtered_headers(upstream.headers.items(), response=True)),
    )


def _filtered_headers(
    headers: Iterable[tuple[str, str]],
    *,
    response: bool = False,
) -> list[tuple[str, str]]:
    blocked = set(_HOP_BY_HOP_HEADERS)
    blocked.add("content-length")
    if response:
        blocked.add("content-encoding")
    else:
        blocked.update({"accept-encoding", "host"})
    return [(key, value) for key, value in headers if key.lower() not in blocked]
