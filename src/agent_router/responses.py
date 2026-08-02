"""Streaming response primitives with deterministic resource cleanup."""

from __future__ import annotations

from inspect import isawaitable
from typing import Any

import structlog
from anyio import CancelScope
from fastapi.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

logger = structlog.get_logger(__name__)


class ManagedStreamingResponse(StreamingResponse):
    """Close the asynchronous response body after completion or disconnect.

    Starlette's streaming loop does not close an async iterator when the ASGI
    ``send`` call fails after a yielded chunk. Closing it in ``finally`` makes
    upstream HTTP contexts and concurrency slots deterministic on disconnects.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Send the response and always finalize its body iterator."""
        try:
            await super().__call__(scope, receive, send)
        finally:
            close = getattr(self.body_iterator, "aclose", None)
            if close is not None:
                try:
                    with CancelScope(shield=True):
                        result: Any = close()
                        if isawaitable(result):
                            await result
                except Exception:
                    logger.warning("streaming_response.close_failed", exc_info=True)
