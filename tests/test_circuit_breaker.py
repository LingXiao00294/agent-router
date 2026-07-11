from __future__ import annotations

import time

import pytest

from agent_router.circuit_breaker import CircuitBreaker, CircuitState
from agent_router.routing import AllProvidersFailedError, Router

# 留出超过 Windows 15.625ms 时钟分辨率的余量，避免 50ms 超时测试抖动。
_RECOVERY_WAIT_SECONDS = 0.1


class TestCircuitBreakerUnit:
    async def test_initial_state_is_closed(self):
        cb = CircuitBreaker()
        assert await cb.state("p1") == CircuitState.CLOSED
        assert await cb.is_available("p1")

    async def test_consecutive_failures_open_circuit(self):
        cb = CircuitBreaker(failure_threshold=3)
        await cb.record_failure("p1")
        assert await cb.state("p1") == CircuitState.CLOSED
        await cb.record_failure("p1")
        assert await cb.state("p1") == CircuitState.CLOSED
        await cb.record_failure("p1")
        assert await cb.state("p1") == CircuitState.OPEN
        assert not await cb.is_available("p1")

    async def test_immediate_failure_opens_circuit(self):
        cb = CircuitBreaker()
        await cb.record_failure("p1", immediate=True)
        assert await cb.state("p1") == CircuitState.OPEN
        assert not await cb.is_available("p1")

    async def test_success_resets_circuit(self):
        cb = CircuitBreaker(failure_threshold=2)
        await cb.record_failure("p1")
        await cb.record_failure("p1")
        assert await cb.state("p1") == CircuitState.OPEN
        await cb.record_success("p1")
        assert await cb.state("p1") == CircuitState.CLOSED
        assert await cb.is_available("p1")

    async def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3)
        await cb.record_failure("p1")
        await cb.record_failure("p1")
        await cb.record_success("p1")
        await cb.record_failure("p1")
        await cb.record_failure("p1")
        assert await cb.state("p1") == CircuitState.CLOSED

    async def test_recovery_timeout_transitions_to_half_open(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05)
        await cb.record_failure("p1")
        assert await cb.state("p1") == CircuitState.OPEN
        time.sleep(_RECOVERY_WAIT_SECONDS)
        assert await cb.state("p1") == CircuitState.HALF_OPEN
        assert await cb.is_available("p1")

    async def test_half_open_success_closes_circuit(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05)
        await cb.record_failure("p1")
        time.sleep(_RECOVERY_WAIT_SECONDS)
        assert await cb.state("p1") == CircuitState.HALF_OPEN
        await cb.record_success("p1")
        assert await cb.state("p1") == CircuitState.CLOSED

    async def test_half_open_failure_reopens_circuit(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05)
        await cb.record_failure("p1")
        time.sleep(_RECOVERY_WAIT_SECONDS)
        assert await cb.state("p1") == CircuitState.HALF_OPEN
        await cb.record_failure("p1")
        assert await cb.state("p1") == CircuitState.OPEN

    async def test_providers_are_independent(self):
        cb = CircuitBreaker(failure_threshold=1)
        await cb.record_failure("p1")
        assert await cb.state("p1") == CircuitState.OPEN
        assert await cb.state("p2") == CircuitState.CLOSED
        assert not await cb.is_available("p1")
        assert await cb.is_available("p2")

    async def test_reset_clears_state(self):
        cb = CircuitBreaker(failure_threshold=1)
        await cb.record_failure("p1")
        assert await cb.state("p1") == CircuitState.OPEN
        await cb.reset("p1")
        assert await cb.state("p1") == CircuitState.CLOSED
        assert await cb.is_available("p1")

    async def test_per_provider_failure_threshold(self):
        """Per-provider threshold overrides global default."""
        cb = CircuitBreaker(failure_threshold=5)
        # p1 uses per-provider threshold of 2
        await cb.record_failure("p1", failure_threshold=2)
        assert await cb.state("p1") == CircuitState.CLOSED
        await cb.record_failure("p1", failure_threshold=2)
        assert await cb.state("p1") == CircuitState.OPEN
        # p2 still uses global threshold of 5
        await cb.record_failure("p2")
        await cb.record_failure("p2")
        assert await cb.state("p2") == CircuitState.CLOSED

    async def test_per_provider_recovery_timeout(self):
        """Per-provider recovery_timeout overrides global default."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=10.0)
        await cb.record_failure("p1")
        assert await cb.state("p1") == CircuitState.OPEN
        # Global timeout (10s) hasn't passed
        assert await cb.state("p1") == CircuitState.OPEN
        # Per-provider timeout (0.05s) should allow transition
        time.sleep(_RECOVERY_WAIT_SECONDS)
        assert await cb.state("p1", recovery_timeout=0.05) == CircuitState.HALF_OPEN

    async def test_per_provider_recovery_timeout_shorter_than_global(self):
        """Shorter per-provider timeout triggers transition before global."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=10.0)
        await cb.record_failure("p1")
        await cb.record_failure("p2")
        time.sleep(_RECOVERY_WAIT_SECONDS)
        # p1 uses short per-provider timeout → HALF_OPEN
        assert await cb.state("p1", recovery_timeout=0.05) == CircuitState.HALF_OPEN
        # p2 uses global timeout (10s) → still OPEN
        assert await cb.state("p2") == CircuitState.OPEN

    async def test_per_provider_is_available(self):
        """is_available respects per-provider recovery_timeout."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=10.0)
        await cb.record_failure("p1")
        assert not await cb.is_available("p1")
        time.sleep(_RECOVERY_WAIT_SECONDS)
        assert not await cb.is_available("p1")  # global timeout
        assert await cb.is_available(
            "p1", recovery_timeout=0.05
        )  # per-provider timeout


class TestCircuitBreakerRouterIntegration:
    """Test that circuit breaker filters providers in Router._get_providers."""

    async def test_open_circuit_excludes_provider(self, sample_config, http_client):
        router = Router(sample_config, http_client)
        providers = await router._get_providers("haiku-router")
        assert len(providers) == 2

        await router.circuit_breaker.record_failure("anthropic", immediate=True)
        providers = await router._get_providers("haiku-router")
        assert len(providers) == 1
        assert providers[0].name == "zhipu"

    async def test_all_open_raises_error(self, sample_config, http_client):
        router = Router(sample_config, http_client)
        await router.circuit_breaker.record_failure("anthropic", immediate=True)
        await router.circuit_breaker.record_failure("zhipu", immediate=True)
        with pytest.raises(AllProvidersFailedError) as exc:
            await router._get_providers("haiku-router")
        assert "熔断" in str(exc.value)
        assert len(exc.value.errors) == 2

    async def test_recovery_restores_provider(self, sample_config, http_client):
        router = Router(sample_config, http_client)
        await router.circuit_breaker.record_failure("anthropic", immediate=True)
        assert len(await router._get_providers("haiku-router")) == 1

        await router.circuit_breaker.record_success("anthropic")
        assert len(await router._get_providers("haiku-router")) == 2
