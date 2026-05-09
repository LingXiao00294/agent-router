from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

import httpx

from agent_router.config import ProviderConfig


class NonRetryableError(Exception):
    """不可重试的错误 (4xx 客户端错误、协议错误等)."""


class RetryableError(Exception):
    """可重试的错误 (5xx、429、超时、连接错误等)."""

    def __init__(self, message: str, *, immediate_break: bool = False) -> None:
        super().__init__(message)
        self.immediate_break = immediate_break


class BaseProvider(ABC):
    def __init__(self, config: ProviderConfig, http_client: httpx.AsyncClient) -> None:
        self.config = config
        self.http = http_client

    @abstractmethod
    async def send(self, request_body: dict) -> dict:
        """非流式请求，返回完整响应 JSON."""

    @abstractmethod
    async def send_stream(self, request_body: dict) -> AsyncIterator[bytes]:
        """流式请求，yield SSE 原始字节."""
