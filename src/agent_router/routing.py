from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import AsyncIterator
from typing import Literal

import structlog
from structlog.contextvars import get_contextvars

from agent_router.circuit_breaker import CircuitBreaker
from agent_router.config import (
    AppConfig,
    ProviderConfig,
    VirtualModelConfig,
    has_unresolved_env_var,
)
from agent_router.provider_gate import (
    ProviderCapacityError,
    ProviderCooldownError,
    ProviderGate,
)
from agent_router.providers.anthropic_compat import AnthropicCompatProvider
from agent_router.providers.base import BaseProvider, NonRetryableError, RetryableError

logger = structlog.get_logger(__name__)

# SSE error event pattern: event: error followed by data: {...}
_SSE_ERROR_EVENT_RE = re.compile(
    rb"event:\s*error\s*\r?\ndata:\s*(\{.*?\})\s*(?:\r?\n|$)", re.DOTALL
)

_RATE_LIMIT_ERROR_TYPES = {
    "rate_limit_error",
    "overloaded_error",
    "overloaded",
}

# Error types that should trigger failover (same as RETRYABLE_STATUSES)
_RETRYABLE_ERROR_TYPES = {
    "rate_limit_error",
    "overloaded_error",
    "api_error",
    "overloaded",
}

# Error types that should immediately circuit break (same as AUTH_STATUSES)
_AUTH_ERROR_TYPES = {
    "authentication_error",
    "permission_error",
}


def _check_stream_error(buffer: bytes) -> None:
    """Check SSE buffer for error events and raise appropriate exception.

    This detects errors in streaming responses that return HTTP 200 but
    contain error events in the stream (like rate limit exceeded).
    """
    m = _SSE_ERROR_EVENT_RE.search(buffer)
    if not m:
        return

    try:
        data = json.loads(m.group(1))
        error = data.get("error", {})
        error_type = error.get("type", "")
        error_message = error.get("message", "Unknown stream error")

        if error_type in _AUTH_ERROR_TYPES:
            raise RetryableError(
                f"Stream error ({error_type}): {error_message}",
                immediate_break=True,
            )
        if error_type in _RATE_LIMIT_ERROR_TYPES:
            raise RetryableError(
                f"Stream error ({error_type}): {error_message}",
                rate_limited=True,
            )
        if error_type in _RETRYABLE_ERROR_TYPES:
            raise RetryableError(f"Stream error ({error_type}): {error_message}")
        # Unknown error types are non-retryable (don't blindly failover)
        raise NonRetryableError(f"Stream error ({error_type}): {error_message}")
    except (json.JSONDecodeError, KeyError, TypeError):
        # Malformed error event — non-retryable since we can't identify the type
        raise NonRetryableError(
            f"Stream error: {m.group(1).decode(errors='replace')[:500]}"
        ) from None


def _create_provider(config: ProviderConfig, http_client) -> BaseProvider:
    if config.type == "anthropic":
        return AnthropicCompatProvider(config, http_client)
    if config.type == "openai":
        raise NotImplementedError("OpenAI provider 尚未实现")
    raise ValueError(f"未知 provider 类型: {config.type}")


def _max_retry_after(errors: list[dict]) -> float | None:
    values = [
        e["retry_after"]
        for e in errors
        if isinstance(e.get("retry_after"), (int, float)) and e["retry_after"] > 0
    ]
    return max(values) if values else None


class Router:
    def __init__(self, config: AppConfig, http_client) -> None:
        self.config = config
        self.http = http_client
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=config.router.failure_threshold,
            recovery_timeout=config.router.recovery_timeout,
        )
        self.provider_gate = ProviderGate()
        self.provider_gate.configure_from_models(config.models)

    async def reload_config(self, new_config: AppConfig) -> None:
        """热重载配置，保留 http_client、熔断器与冷却状态."""
        self.config = new_config
        self.circuit_breaker.failure_threshold = new_config.router.failure_threshold
        self.circuit_breaker.recovery_timeout = new_config.router.recovery_timeout
        self.provider_gate.configure_from_models(new_config.models)

    def _virtual_model(self, name: str) -> VirtualModelConfig:
        if name not in self.config.models:
            raise UnknownModelError(name, list(self.config.models.keys()))
        return self.config.models[name]

    async def _handle_provider_error(
        self,
        e: RetryableError | NonRetryableError,
        provider_cfg: ProviderConfig,
        request_id: str,
        p_start: float,
        errors: list[dict],
        outcome: dict | None,
        providers: list[ProviderConfig],
        i: int,
        *,
        allow_failover: bool,
    ) -> None:
        """Shared error handling for both route methods.

        For NonRetryableError, re-raises after logging.
        For sticky mode (allow_failover=False), re-raises retryable errors too.
        """
        p_latency = (time.time() - p_start) * 1000
        is_retryable = isinstance(e, RetryableError)
        rate_limited = is_retryable and e.rate_limited
        retry_after: float | None = None

        if is_retryable and rate_limited:
            retry_after = self.provider_gate.enter_cooldown(
                provider_cfg.name,
                e.retry_after
                if e.retry_after is not None
                else provider_cfg.rate_limit_cooldown,
            )
        elif is_retryable:
            await self.circuit_breaker.record_failure(
                provider_cfg.name,
                immediate=e.immediate_break,
                failure_threshold=provider_cfg.failure_threshold,
            )

        err_entry: dict = {
            "provider": provider_cfg.name,
            "model": provider_cfg.model,
            "priority": provider_cfg.priority,
            "error": str(e),
            "retryable": is_retryable,
            "rate_limited": rate_limited,
            "latency_ms": round(p_latency),
        }
        if retry_after is not None:
            err_entry["retry_after"] = retry_after
        errors.append(err_entry)

        if is_retryable and outcome is not None:
            outcome.setdefault("_failures", []).append(
                {
                    "provider": provider_cfg.name,
                    "model": provider_cfg.model,
                    "error": str(e),
                    "latency_ms": round(p_latency),
                }
            )

        log_fn = logger.warning if is_retryable else logger.error
        log_fn(
            "provider.fail",
            request_id=request_id,
            provider=provider_cfg.name,
            model=provider_cfg.model,
            error=str(e),
            retry=is_retryable,
            rate_limited=rate_limited,
            provider_latency_ms=round(p_latency),
        )

        if not is_retryable:
            raise e

        if not allow_failover:
            if rate_limited:
                raise StickyRateLimited(retry_after)
            # sticky：不转移；可重试失败记入 errors，由调用方循环结束后统一抛出
            return

        next_idx = i + 1
        if next_idx < len(providers):
            next_cfg = providers[next_idx]
            logger.info(
                "failover",
                request_id=request_id,
                from_provider=provider_cfg.name,
                from_model=provider_cfg.model,
                to_provider=next_cfg.name,
                to_model=next_cfg.model,
                reason="rate_limited" if rate_limited else "retryable_error",
                circuit_broken=e.immediate_break,
            )

    async def _record_gate_skip(
        self,
        e: ProviderCooldownError | ProviderCapacityError,
        provider_cfg: ProviderConfig,
        request_id: str,
        p_start: float,
        errors: list[dict],
        outcome: dict | None,
        providers: list[ProviderConfig],
        i: int,
        *,
        allow_failover: bool,
        virtual_model: str,
    ) -> None:
        p_latency = (time.time() - p_start) * 1000
        kind = "rate_limit" if isinstance(e, ProviderCooldownError) else "capacity"
        retry_after = e.retry_after
        err_entry: dict = {
            "provider": provider_cfg.name,
            "model": provider_cfg.model,
            "priority": provider_cfg.priority,
            "error": str(e),
            "retryable": True,
            "rate_limited": kind == "rate_limit",
            "capacity": kind == "capacity",
            "latency_ms": round(p_latency),
        }
        if retry_after is not None:
            err_entry["retry_after"] = retry_after
        errors.append(err_entry)

        if outcome is not None:
            outcome.setdefault("_failures", []).append(
                {
                    "provider": provider_cfg.name,
                    "model": provider_cfg.model,
                    "error": str(e),
                    "latency_ms": round(p_latency),
                }
            )

        logger.warning(
            "provider.gate_skip",
            request_id=request_id,
            provider=provider_cfg.name,
            model=provider_cfg.model,
            kind=kind,
            error=str(e),
            provider_latency_ms=round(p_latency),
        )

        if not allow_failover:
            raise NoProviderAvailableError(
                virtual_model,
                errors,
                kind=kind,
                retry_after=retry_after,
            )

        next_idx = i + 1
        if next_idx < len(providers):
            next_cfg = providers[next_idx]
            logger.info(
                "failover",
                request_id=request_id,
                from_provider=provider_cfg.name,
                from_model=provider_cfg.model,
                to_provider=next_cfg.name,
                to_model=next_cfg.model,
                reason=kind,
            )

    async def route_non_stream(
        self, request_body: dict, outcome: dict | None = None
    ) -> dict:
        """非流式路由: 返回第一个成功 provider 的响应 JSON.

        outcome 可选字典，成功时会写入 provider_type, provider_model, attempt, base_url.
        """
        virtual_model = request_body.get("model", "")
        allow_failover = self.config.router.mode == "failover"
        providers = await self._get_providers(virtual_model)

        request_id = get_contextvars().get("request_id") or str(uuid.uuid4())
        start_time = time.time()
        errors: list[dict] = []

        logger.info(
            "request.start",
            request_id=request_id,
            model=virtual_model,
            stream=False,
            mode=self.config.router.mode,
            provider_count=len(providers),
        )

        for i, provider_cfg in enumerate(providers):
            attempt = i + 1
            p_start = time.time()

            logger.info(
                "provider.try",
                request_id=request_id,
                provider=provider_cfg.name,
                model=provider_cfg.model,
                priority=provider_cfg.priority,
                attempt=attempt,
            )

            try:
                async with self.provider_gate.slot(provider_cfg):
                    provider = _create_provider(provider_cfg, self.http)
                    result = await provider.send(request_body)
                    p_latency = (time.time() - p_start) * 1000
                    total_latency = (time.time() - start_time) * 1000

                    await self.circuit_breaker.record_success(provider_cfg.name)

                    logger.info(
                        "provider.success",
                        request_id=request_id,
                        provider=provider_cfg.name,
                        model=provider_cfg.model,
                        attempt=attempt,
                        provider_latency_ms=round(p_latency),
                        total_latency_ms=round(total_latency),
                    )

                    if outcome is not None:
                        outcome["provider_type"] = provider_cfg.type
                        outcome["provider_name"] = provider_cfg.name
                        outcome["provider_model"] = provider_cfg.model
                        outcome["provider_url"] = provider_cfg.base_url
                        outcome["attempt"] = attempt

                    return result

            except (ProviderCooldownError, ProviderCapacityError) as e:
                await self._record_gate_skip(
                    e,
                    provider_cfg,
                    request_id,
                    p_start,
                    errors,
                    outcome,
                    providers,
                    i,
                    allow_failover=allow_failover,
                    virtual_model=virtual_model,
                )
            except (RetryableError, NonRetryableError) as e:
                try:
                    await self._handle_provider_error(
                        e,
                        provider_cfg,
                        request_id,
                        p_start,
                        errors,
                        outcome,
                        providers,
                        i,
                        allow_failover=allow_failover,
                    )
                except StickyRateLimited as srl:
                    raise NoProviderAvailableError(
                        virtual_model,
                        errors,
                        kind="rate_limit",
                        retry_after=srl.retry_after,
                    ) from e

        raise self._exhausted(virtual_model, errors, start_time, len(providers))

    async def route_stream(
        self, request_body: dict, outcome: dict | None = None
    ) -> AsyncIterator[bytes]:
        """流式路由: 返回第一个成功 provider 的 SSE 流.

        outcome 可选字典，成功时会写入 provider_type, provider_model, attempt, base_url.
        """
        virtual_model = request_body.get("model", "")
        allow_failover = self.config.router.mode == "failover"
        providers = await self._get_providers(virtual_model)

        request_id = get_contextvars().get("request_id") or str(uuid.uuid4())
        start_time = time.time()
        errors: list[dict] = []

        logger.info(
            "request.start",
            request_id=request_id,
            model=virtual_model,
            stream=True,
            mode=self.config.router.mode,
            provider_count=len(providers),
        )

        # 一旦向客户端 yield 过字节，禁止再 failover，避免拼接多路 SSE
        client_started = False

        for i, provider_cfg in enumerate(providers):
            attempt = i + 1
            p_start = time.time()

            logger.info(
                "provider.try",
                request_id=request_id,
                provider=provider_cfg.name,
                model=provider_cfg.model,
                priority=provider_cfg.priority,
                attempt=attempt,
            )

            try:
                async with self.provider_gate.slot(provider_cfg):
                    provider = _create_provider(provider_cfg, self.http)
                    error_buffer = b""
                    async for chunk in provider.send_stream(request_body):
                        error_buffer += chunk
                        if len(error_buffer) > 8192:
                            error_buffer = error_buffer[-4096:]
                        # 先发给客户端再检测流内错误，避免已输出半截后仍 failover
                        client_started = True
                        yield chunk
                        _check_stream_error(error_buffer)
                    p_latency = (time.time() - p_start) * 1000
                    total_latency = (time.time() - start_time) * 1000

                    await self.circuit_breaker.record_success(provider_cfg.name)

                    logger.info(
                        "provider.success",
                        request_id=request_id,
                        provider=provider_cfg.name,
                        model=provider_cfg.model,
                        attempt=attempt,
                        provider_latency_ms=round(p_latency),
                        total_latency_ms=round(total_latency),
                    )

                    if outcome is not None:
                        outcome["provider_type"] = provider_cfg.type
                        outcome["provider_name"] = provider_cfg.name
                        outcome["provider_model"] = provider_cfg.model
                        outcome["provider_url"] = provider_cfg.base_url
                        outcome["attempt"] = attempt

                    return

            except (ProviderCooldownError, ProviderCapacityError) as e:
                can_failover = allow_failover and not client_started
                await self._record_gate_skip(
                    e,
                    provider_cfg,
                    request_id,
                    p_start,
                    errors,
                    outcome,
                    providers,
                    i,
                    allow_failover=can_failover,
                    virtual_model=virtual_model,
                )
                if client_started:
                    raise
            except (RetryableError, NonRetryableError) as e:
                can_failover = allow_failover and not client_started
                try:
                    await self._handle_provider_error(
                        e,
                        provider_cfg,
                        request_id,
                        p_start,
                        errors,
                        outcome,
                        providers,
                        i,
                        allow_failover=can_failover,
                    )
                except StickyRateLimited as srl:
                    raise NoProviderAvailableError(
                        virtual_model,
                        errors,
                        kind="rate_limit",
                        retry_after=srl.retry_after,
                    ) from e
                if client_started:
                    # 已向客户端发送数据后不再 failover；可重试错误也直接抛出
                    raise

        raise self._exhausted(virtual_model, errors, start_time, len(providers))

    def _exhausted(
        self,
        virtual_model: str,
        errors: list[dict],
        start_time: float,
        attempts: int,
    ) -> Exception:
        total_latency = (time.time() - start_time) * 1000
        logger.error(
            "failover.exhausted",
            model=virtual_model,
            attempts=attempts,
            total_latency_ms=round(total_latency),
            errors=errors,
        )
        if errors and all(e.get("rate_limited") or e.get("capacity") for e in errors):
            if any(e.get("capacity") for e in errors) and not any(
                e.get("rate_limited") for e in errors
            ):
                kind: Literal["capacity", "rate_limit"] = "capacity"
            elif any(e.get("rate_limited") for e in errors):
                kind = "rate_limit"
            else:
                kind = "capacity"
            return NoProviderAvailableError(
                virtual_model,
                errors,
                kind=kind,
                retry_after=_max_retry_after(errors),
            )
        return AllProvidersFailedError(virtual_model, errors)

    async def _get_providers(self, virtual_model: str) -> list[ProviderConfig]:
        vm = self._virtual_model(virtual_model)
        mode = self.config.router.mode

        if mode == "sticky":
            if not vm.pinned_provider or not vm.pinned_model:
                raise AllProvidersFailedError(
                    virtual_model,
                    [
                        {
                            "provider": "(none)",
                            "model": "(none)",
                            "error": ("sticky 模式未配置 pinned_provider/pinned_model"),
                            "retryable": False,
                        }
                    ],
                )
            candidates = [
                p
                for p in vm.providers
                if p.name == vm.pinned_provider and p.model == vm.pinned_model
            ]
            if not candidates:
                raise AllProvidersFailedError(
                    virtual_model,
                    [
                        {
                            "provider": vm.pinned_provider,
                            "model": vm.pinned_model,
                            "error": (
                                "sticky 指定的 provider:model 不在该虚拟模型链中"
                            ),
                            "retryable": False,
                        }
                    ],
                )
        else:
            candidates = list(vm.providers)

        available: list[ProviderConfig] = []
        skipped: list[dict] = []

        for p in candidates:
            if has_unresolved_env_var(p.api_key):
                skipped.append(
                    {
                        "provider": p.name,
                        "model": p.model,
                        "reason": "unresolved_api_key",
                        "error": (f"api_key 环境变量未设置或未正确插值: {p.api_key}"),
                        "retryable": False,
                    }
                )
                continue

            if not await self.circuit_breaker.is_available(
                p.name, recovery_timeout=p.recovery_timeout
            ):
                skipped.append(
                    {
                        "provider": p.name,
                        "model": p.model,
                        "state": (
                            await self.circuit_breaker.state(
                                p.name, recovery_timeout=p.recovery_timeout
                            )
                        ).value,
                        "retryable": True,
                        "reason": "circuit_open",
                    }
                )
                continue

            remaining = self.provider_gate.cooldown_remaining(p.name)
            if remaining > 0:
                # sticky: 仍返回该 provider，由 slot() 抛出冷却错误 → 429
                # failover: 跳过，尝试下一个
                if mode == "failover":
                    skipped.append(
                        {
                            "provider": p.name,
                            "model": p.model,
                            "reason": "cooldown",
                            "error": (
                                f"provider 处于限流冷却 (remaining={remaining:.1f}s)"
                            ),
                            "retryable": True,
                            "rate_limited": True,
                            "retry_after": remaining,
                        }
                    )
                    continue

            available.append(p)

        if skipped:
            logger.info(
                "providers.skipped",
                model=virtual_model,
                mode=mode,
                skipped=skipped,
                available_count=len(available),
            )

        if not available and skipped:
            if all(
                s.get("reason") == "cooldown" or s.get("rate_limited") for s in skipped
            ):
                raise NoProviderAvailableError(
                    virtual_model,
                    [
                        {
                            "provider": s["provider"],
                            "model": s["model"],
                            "error": s.get("error", "cooldown"),
                            "retryable": True,
                            "rate_limited": True,
                            "retry_after": s.get("retry_after"),
                        }
                        for s in skipped
                    ],
                    kind="rate_limit",
                    retry_after=_max_retry_after(skipped),
                )
            raise AllProvidersFailedError(
                virtual_model,
                [
                    {
                        "provider": s["provider"],
                        "model": s["model"],
                        "error": s["error"]
                        if "error" in s
                        else f"provider 已熔断 (state={s.get('state')})",
                        "retryable": s.get("retryable", True),
                    }
                    for s in skipped
                ],
            )

        return available

    @property
    def model_names(self) -> list[str]:
        return list(self.config.models.keys())


class StickyRateLimited(Exception):
    """Internal: sticky mode hit rate limit; convert to NoProviderAvailableError."""

    def __init__(self, retry_after: float | None) -> None:
        self.retry_after = retry_after


class UnknownModelError(Exception):
    def __init__(self, model: str, known: list[str]) -> None:
        self.model = model
        self.known = known
        super().__init__(f"未知模型 '{model}'，已知模型: {', '.join(known)}")


class AllProvidersFailedError(Exception):
    def __init__(self, model: str, errors: list[dict]) -> None:
        self.model = model
        self.errors = errors
        summary = "; ".join(
            f"[{e['provider']}:{e['model']}] {e['error']}" for e in errors
        )
        super().__init__(f"模型 '{model}' 所有 provider 均失败: {summary}")


class NoProviderAvailableError(Exception):
    """本地容量耗尽或上游限流导致无可用 provider."""

    def __init__(
        self,
        model: str,
        errors: list[dict],
        *,
        kind: Literal["capacity", "rate_limit"],
        retry_after: float | None = None,
    ) -> None:
        self.model = model
        self.errors = errors
        self.kind = kind
        self.retry_after = retry_after
        label = "本地容量不足" if kind == "capacity" else "上游限流"
        summary = "; ".join(
            f"[{e['provider']}:{e['model']}] {e['error']}" for e in errors
        )
        super().__init__(f"模型 '{model}' {label}: {summary}")
