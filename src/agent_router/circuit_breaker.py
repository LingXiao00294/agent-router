from __future__ import annotations

import threading
import time
from enum import Enum

from structlog import get_logger

logger = get_logger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Per-provider circuit breaker.

    CLOSED  → normal operation, requests pass through.
    OPEN    → circuit tripped, requests rejected until recovery_timeout.
    HALF_OPEN → one probe request allowed to test recovery.

    Parameters
    ----------
    failure_threshold:
        Consecutive failures before opening the circuit.
    recovery_timeout:
        Seconds to wait in OPEN state before transitioning to HALF_OPEN.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 600.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failure_counts: dict[str, int] = {}
        self._states: dict[str, CircuitState] = {}
        self._last_failure_time: dict[str, float] = {}
        self._lock = threading.Lock()

    def state(self, provider: str, recovery_timeout: float | None = None) -> CircuitState:
        timeout = recovery_timeout if recovery_timeout is not None else self.recovery_timeout
        with self._lock:
            current = self._states.get(provider, CircuitState.CLOSED)
            if current == CircuitState.OPEN:
                elapsed = time.monotonic() - self._last_failure_time.get(provider, 0)
                if elapsed >= timeout:
                    self._states[provider] = CircuitState.HALF_OPEN
                    logger.info(
                        "circuit.half_open",
                        provider=provider,
                        recovery_timeout=timeout,
                    )
                    return CircuitState.HALF_OPEN
            return current

    def is_available(self, provider: str, recovery_timeout: float | None = None) -> bool:
        return self.state(provider, recovery_timeout=recovery_timeout) != CircuitState.OPEN

    def record_success(self, provider: str) -> None:
        with self._lock:
            prev = self._states.get(provider, CircuitState.CLOSED)
            self._failure_counts.pop(provider, None)
            self._states[provider] = CircuitState.CLOSED
        if prev != CircuitState.CLOSED:
            logger.info(
                "circuit.closed",
                provider=provider,
                prev_state=prev.value,
                msg="provider recovered, circuit breaker closed",
            )

    def record_failure(
        self,
        provider: str,
        *,
        immediate: bool = False,
        failure_threshold: int | None = None,
    ) -> None:
        threshold = failure_threshold if failure_threshold is not None else self.failure_threshold
        with self._lock:
            if immediate:
                self._failure_counts[provider] = threshold
                self._states[provider] = CircuitState.OPEN
                self._last_failure_time[provider] = time.monotonic()
                logger.warning(
                    "circuit.opened",
                    provider=provider,
                    reason="auth_error",
                    msg="auth/permission error, circuit breaker immediately opened",
                    recovery_timeout=self.recovery_timeout,
                )
                return

            count = self._failure_counts.get(provider, 0) + 1
            self._failure_counts[provider] = count

            if count >= threshold:
                self._states[provider] = CircuitState.OPEN
                self._last_failure_time[provider] = time.monotonic()
                logger.warning(
                    "circuit.opened",
                    provider=provider,
                    reason="consecutive_failures",
                    failures=count,
                    threshold=threshold,
                    recovery_timeout=self.recovery_timeout,
                    msg=f"consecutive failures reached threshold ({count}/{threshold})",
                )
            else:
                logger.debug(
                    "circuit.failure_counted",
                    provider=provider,
                    consecutive_failures=count,
                    threshold=threshold,
                )

    def reset(self, provider: str) -> None:
        with self._lock:
            self._failure_counts.pop(provider, None)
            self._states.pop(provider, None)
            self._last_failure_time.pop(provider, None)

    def get_all_states(self) -> dict[str, CircuitState]:
        """Return current state of all known providers."""
        with self._lock:
            return {
                p: self._states.get(p, CircuitState.CLOSED)
                for p in set(self._states) | set(self._failure_counts)
            }
