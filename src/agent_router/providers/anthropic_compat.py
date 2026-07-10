from __future__ import annotations

from collections.abc import AsyncIterator
from email.utils import parsedate_to_datetime
from time import time

import httpx
from structlog import get_logger

from agent_router.providers.base import BaseProvider, NonRetryableError, RetryableError

logger = get_logger(__name__)

RATE_LIMIT_STATUSES: set[int] = {429, 529}
RETRYABLE_STATUSES: set[int] = {429, 500, 502, 503, 504, 529}
AUTH_STATUSES: set[int] = {401, 403}
RETRYABLE_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
    httpx.PoolTimeout,
)


def parse_retry_after(value: str | None) -> float | None:
    """Parse Retry-After header (delay-seconds or HTTP-date) to seconds."""
    if not value:
        return None
    value = value.strip()
    try:
        seconds = float(value)
        if seconds >= 0:
            return seconds
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(value)
        delay = dt.timestamp() - time()
        return max(0.0, delay)
    except (TypeError, ValueError, OverflowError):
        return None


def _classify_error(e: httpx.HTTPStatusError) -> Exception:
    status = e.response.status_code
    body = e.response.text[:500]
    if status in AUTH_STATUSES:
        return RetryableError(
            f"HTTP {status}: {body}",
            immediate_break=True,
        )
    if status in RATE_LIMIT_STATUSES:
        retry_after = parse_retry_after(e.response.headers.get("Retry-After"))
        return RetryableError(
            f"HTTP {status}: {body}",
            rate_limited=True,
            retry_after=retry_after,
        )
    if status in RETRYABLE_STATUSES:
        return RetryableError(f"HTTP {status}: {body}")
    return NonRetryableError(f"HTTP {status}: {body}")


def _classify_exception(e: Exception) -> Exception:
    if isinstance(e, RETRYABLE_EXCEPTIONS):
        return RetryableError(str(e))
    return NonRetryableError(str(e))


class AnthropicCompatProvider(BaseProvider):
    """Anthropic Messages API 兼容直通适配器.

    适用于 Anthropic 官方 API 及兼容 Anthropic 格式的第三方 API (如智谱 GLM).
    """

    async def send(self, request_body: dict) -> dict:
        url = f"{self.config.base_url}/v1/messages"
        headers = self._build_headers(request_body)
        modified_body = self._prepare_body(request_body)

        try:
            response = await self.http.post(
                url,
                json=modified_body,
                headers=headers,
                timeout=self.config.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise _classify_error(e) from e
        except Exception as e:
            raise _classify_exception(e) from e

        try:
            return response.json()
        except Exception as e:
            raise NonRetryableError("响应不是有效的 JSON") from e

    async def send_stream(self, request_body: dict) -> AsyncIterator[bytes]:
        url = f"{self.config.base_url}/v1/messages"
        headers = self._build_headers(request_body)
        headers["Accept-Encoding"] = "identity"
        modified_body = {**self._prepare_body(request_body), "stream": True}

        try:
            async with self.http.stream(
                "POST",
                url,
                json=modified_body,
                headers=headers,
                timeout=self.config.timeout_seconds,
            ) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as e:
                    await e.response.aread()
                    raise _classify_error(e) from e

                async for chunk in response.aiter_bytes():
                    yield chunk
        except (NonRetryableError, RetryableError):
            raise
        except Exception as e:
            raise _classify_exception(e) from e

    def _build_headers(self, request_body: dict) -> dict:
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": request_body.get("anthropic_version", "2023-06-01"),
        }
        # 尝试多种认证 header 格式
        if self.config.api_key.startswith("sk-ant"):
            headers["x-api-key"] = self.config.api_key
        else:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def _prepare_body(self, request_body: dict) -> dict:
        body = {**request_body}
        body["model"] = self.config.model
        return body
