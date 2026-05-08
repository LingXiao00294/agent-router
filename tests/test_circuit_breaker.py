from __future__ import annotations

import time

import pytest

from agent_router.circuit_breaker import CircuitBreaker, CircuitState
from agent_router.routing import AllProvidersFailedError, Router


class TestCircuitBreakerUnit:
    def test_initial_state_is_closed(self):
        cb = CircuitBreaker()
        assert cb.state("p1") == CircuitState.CLOSED
        assert cb.is_available("p1")

    def test_consecutive_failures_open_circuit(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure("p1")
        assert cb.state("p1") == CircuitState.CLOSED
        cb.record_failure("p1")
        assert cb.state("p1") == CircuitState.CLOSED
        cb.record_failure("p1")
        assert cb.state("p1") == CircuitState.OPEN
        assert not cb.is_available("p1")

    def test_immediate_failure_opens_circuit(self):
        cb = CircuitBreaker()
        cb.record_failure("p1", immediate=True)
        assert cb.state("p1") == CircuitState.OPEN
        assert not cb.is_available("p1")

    def test_success_resets_circuit(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure("p1")
        cb.record_failure("p1")
        assert cb.state("p1") == CircuitState.OPEN
        cb.record_success("p1")
        assert cb.state("p1") == CircuitState.CLOSED
        assert cb.is_available("p1")

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure("p1")
        cb.record_failure("p1")
        cb.record_success("p1")
        cb.record_failure("p1")
        cb.record_failure("p1")
        assert cb.state("p1") == CircuitState.CLOSED

    def test_recovery_timeout_transitions_to_half_open(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05)
        cb.record_failure("p1")
        assert cb.state("p1") == CircuitState.OPEN
        time.sleep(0.06)
        assert cb.state("p1") == CircuitState.HALF_OPEN
        assert cb.is_available("p1")

    def test_half_open_success_closes_circuit(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05)
        cb.record_failure("p1")
        time.sleep(0.06)
        assert cb.state("p1") == CircuitState.HALF_OPEN
        cb.record_success("p1")
        assert cb.state("p1") == CircuitState.CLOSED

    def test_half_open_failure_reopens_circuit(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05)
        cb.record_failure("p1")
        time.sleep(0.06)
        assert cb.state("p1") == CircuitState.HALF_OPEN
        cb.record_failure("p1")
        assert cb.state("p1") == CircuitState.OPEN

    def test_providers_are_independent(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure("p1")
        assert cb.state("p1") == CircuitState.OPEN
        assert cb.state("p2") == CircuitState.CLOSED
        assert not cb.is_available("p1")
        assert cb.is_available("p2")

    def test_reset_clears_state(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure("p1")
        assert cb.state("p1") == CircuitState.OPEN
        cb.reset("p1")
        assert cb.state("p1") == CircuitState.CLOSED
        assert cb.is_available("p1")


class TestCircuitBreakerRouterIntegration:
    """Test that circuit breaker filters providers in Router._get_providers."""

    def test_open_circuit_excludes_provider(self, sample_config, http_client):
        router = Router(sample_config, http_client)
        providers = router._get_providers("haiku-router")
        assert len(providers) == 2

        router.circuit_breaker.record_failure("anthropic", immediate=True)
        providers = router._get_providers("haiku-router")
        assert len(providers) == 1
        assert providers[0].name == "zhipu"

    def test_all_open_raises_error(self, sample_config, http_client):
        router = Router(sample_config, http_client)
        router.circuit_breaker.record_failure("anthropic", immediate=True)
        router.circuit_breaker.record_failure("zhipu", immediate=True)
        with pytest.raises(AllProvidersFailedError) as exc:
            router._get_providers("haiku-router")
        assert "熔断" in str(exc.value)
        assert len(exc.value.errors) == 2

    def test_recovery_restores_provider(self, sample_config, http_client):
        router = Router(sample_config, http_client)
        router.circuit_breaker.record_failure("anthropic", immediate=True)
        assert len(router._get_providers("haiku-router")) == 1

        router.circuit_breaker.record_success("anthropic")
        assert len(router._get_providers("haiku-router")) == 2
