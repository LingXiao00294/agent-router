"""Tests for ProviderGate: concurrency, queue, cooldown."""

from __future__ import annotations

import asyncio

import pytest

from agent_router.config import ProviderConfig
from agent_router.provider_gate import (
    ProviderCapacityError,
    ProviderCooldownError,
    ProviderGate,
)


def _cfg(
    name: str = "p1",
    *,
    max_concurrent: int = 0,
    max_queue: int = 0,
    queue_wait_timeout: float = 0.2,
    rate_limit_cooldown: float = 1.0,
) -> ProviderConfig:
    return ProviderConfig(
        type="anthropic",
        name=name,
        model="m",
        api_key="k",
        base_url="https://example.com",
        priority=1,
        max_concurrent=max_concurrent,
        max_queue=max_queue,
        queue_wait_timeout=queue_wait_timeout,
        rate_limit_cooldown=rate_limit_cooldown,
    )


class TestProviderGateConcurrency:
    async def test_unlimited_by_default(self):
        gate = ProviderGate()
        cfg = _cfg(max_concurrent=0)
        async with gate.slot(cfg):
            async with gate.slot(cfg):
                pass

    async def test_max_concurrent_blocks_without_queue(self):
        gate = ProviderGate()
        cfg = _cfg(max_concurrent=1, max_queue=0)
        entered = asyncio.Event()
        release = asyncio.Event()

        async def holder():
            async with gate.slot(cfg):
                entered.set()
                await release.wait()

        task = asyncio.create_task(holder())
        await entered.wait()
        with pytest.raises(ProviderCapacityError) as exc:
            async with gate.slot(cfg):
                pass
        assert "并发已满" in str(exc.value)
        release.set()
        await task

    async def test_queue_overflow(self):
        gate = ProviderGate()
        cfg = _cfg(max_concurrent=1, max_queue=1, queue_wait_timeout=2.0)
        entered = asyncio.Event()
        release = asyncio.Event()

        async def holder():
            async with gate.slot(cfg):
                entered.set()
                await release.wait()

        async def waiter():
            async with gate.slot(cfg):
                pass

        task = asyncio.create_task(holder())
        await entered.wait()
        wait_task = asyncio.create_task(waiter())
        await asyncio.sleep(0.05)
        with pytest.raises(ProviderCapacityError) as exc:
            async with gate.slot(cfg):
                pass
        assert "等待队列已满" in str(exc.value)
        release.set()
        await task
        await wait_task

    async def test_queue_wait_timeout(self):
        gate = ProviderGate()
        cfg = _cfg(max_concurrent=1, max_queue=2, queue_wait_timeout=0.05)
        entered = asyncio.Event()
        release = asyncio.Event()

        async def holder():
            async with gate.slot(cfg):
                entered.set()
                await release.wait()

        task = asyncio.create_task(holder())
        await entered.wait()
        with pytest.raises(ProviderCapacityError) as exc:
            async with gate.slot(cfg):
                pass
        assert "排队等待超时" in str(exc.value)
        release.set()
        await task


class TestProviderGateCooldown:
    async def test_enter_and_block(self):
        gate = ProviderGate()
        cfg = _cfg(rate_limit_cooldown=30.0)
        gate.enter_cooldown("p1", 30.0)
        assert gate.is_in_cooldown("p1")
        with pytest.raises(ProviderCooldownError) as exc:
            async with gate.slot(cfg):
                pass
        assert exc.value.retry_after > 0

    async def test_cooldown_expires(self):
        gate = ProviderGate()
        cfg = _cfg()
        gate.enter_cooldown("p1", 0.05)
        await asyncio.sleep(0.06)
        assert not gate.is_in_cooldown("p1")
        async with gate.slot(cfg):
            pass

    async def test_default_cooldown_from_config(self):
        gate = ProviderGate()
        cfg = _cfg(rate_limit_cooldown=12.0)
        gate.configure([cfg])
        duration = gate.enter_cooldown("p1")
        assert duration == 12.0
