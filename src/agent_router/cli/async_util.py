from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """在同步 CLI 上下文中运行协程."""
    return asyncio.run(coro)
