from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import AsyncIterator

import structlog

from agent_router.circuit_breaker import CircuitBreaker
from agent_router.config import AppConfig, ProviderConfig
from agent_router.providers.anthropic_compat import AnthropicCompatProvider
from agent_router.providers.base import BaseProvider, NonRetryableError, RetryableError

logger = structlog.get_logger(__name__)

# SSE error event pattern: event: error followed by data: {...}
_SSE_ERROR_EVENT_RE = re.compile(
    rb"event:\s*error\s*\r?\ndata:\s*(\{.*?\})\s*(?:\r?\n|$)", re.DOTALL
)

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
        if error_type in _RETRYABLE_ERROR_TYPES:
            raise RetryableError(f"Stream error ({error_type}): {error_message}")
        # Unknown error types are non-retryable (don't blindly failover)
        raise NonRetryableError(f"Stream error ({error_type}): {error_message}")
    except (json.JSONDecodeError, KeyError, TypeError):
        # Malformed error event — non-retryable since we can't identify the type
        raise NonRetryableError(f"Stream error: {m.group(1).decode(errors='replace')[:500]}")


def _create_provider(config: ProviderConfig, http_client) -> BaseProvider:
    if config.type == "anthropic":
        return AnthropicCompatProvider(config, http_client)
    if config.type == "openai":
        raise NotImplementedError("OpenAI provider 尚未实现")
    raise ValueError(f"未知 provider 类型: {config.type}")


class Router:
    def __init__(self, config: AppConfig, http_client) -> None:
        self.config = config
        self.http = http_client
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=config.router.failure_threshold,
            recovery_timeout=config.router.recovery_timeout,
        )

    async def route_non_stream(
        self, request_body: dict, outcome: dict | None = None
    ) -> dict:
        """非流式路由: 返回第一个成功 provider 的响应 JSON.

        outcome 可选字典，成功时会写入 provider_type, provider_model, attempt, base_url.
        """
        virtual_model = request_body.get("model", "")
        providers = self._get_providers(virtual_model)

        request_id = str(uuid.uuid4())
        start_time = time.time()
        errors: list[dict] = []

        logger.info(
            "request.start",
            request_id=request_id,
            model=virtual_model,
            stream=False,
            provider_count=len(providers),
        )

        for i, provider_cfg in enumerate(providers):
            attempt = i + 1

            logger.info(
                "provider.try",
                request_id=request_id,
                provider=provider_cfg.name,
                model=provider_cfg.model,
                priority=provider_cfg.priority,
                attempt=attempt,
            )

            try:
                p_start = time.time()
                provider = _create_provider(provider_cfg, self.http)
                result = await provider.send(request_body)
                p_latency = (time.time() - p_start) * 1000
                total_latency = (time.time() - start_time) * 1000

                self.circuit_breaker.record_success(provider_cfg.name)

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

            except RetryableError as e:
                p_latency = (time.time() - p_start) * 1000
                self.circuit_breaker.record_failure(
                    provider_cfg.name, immediate=e.immediate_break
                )
                errors.append(
                    {
                        "provider": provider_cfg.name,
                        "model": provider_cfg.model,
                        "priority": provider_cfg.priority,
                        "error": str(e),
                        "retryable": True,
                    }
                )
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
                    "provider.fail",
                    request_id=request_id,
                    provider=provider_cfg.name,
                    model=provider_cfg.model,
                    error=str(e),
                    retry=True,
                    provider_latency_ms=round(p_latency),
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
                        reason="retryable_error",
                        circuit_broken=e.immediate_break,
                    )

            except NonRetryableError as e:
                p_latency = (time.time() - p_start) * 1000
                errors.append(
                    {
                        "provider": provider_cfg.name,
                        "model": provider_cfg.model,
                        "priority": provider_cfg.priority,
                        "error": str(e),
                        "retryable": False,
                        "latency_ms": round(p_latency),
                    }
                )
                logger.error(
                    "provider.fail",
                    request_id=request_id,
                    provider=provider_cfg.name,
                    model=provider_cfg.model,
                    error=str(e),
                    retry=False,
                    provider_latency_ms=round(p_latency),
                )
                raise

        # 全部失败
        total_latency = (time.time() - start_time) * 1000
        logger.error(
            "failover.exhausted",
            request_id=request_id,
            model=virtual_model,
            attempts=len(providers),
            total_latency_ms=round(total_latency),
            errors=errors,
        )
        raise AllProvidersFailedError(virtual_model, errors)

    async def route_stream(
        self, request_body: dict, outcome: dict | None = None
    ) -> AsyncIterator[bytes]:
        """流式路由: 返回第一个成功 provider 的 SSE 流.

        outcome 可选字典，成功时会写入 provider_type, provider_model, attempt, base_url.
        """
        virtual_model = request_body.get("model", "")
        providers = self._get_providers(virtual_model)

        request_id = str(uuid.uuid4())
        start_time = time.time()
        errors: list[dict] = []

        logger.info(
            "request.start",
            request_id=request_id,
            model=virtual_model,
            stream=True,
            provider_count=len(providers),
        )

        for i, provider_cfg in enumerate(providers):
            attempt = i + 1

            logger.info(
                "provider.try",
                request_id=request_id,
                provider=provider_cfg.name,
                model=provider_cfg.model,
                priority=provider_cfg.priority,
                attempt=attempt,
            )

            try:
                p_start = time.time()
                provider = _create_provider(provider_cfg, self.http)
                error_buffer = b""
                async for chunk in provider.send_stream(request_body):
                    error_buffer += chunk
                    # Limit error detection buffer, keeping recent data for SSE error events
                    if len(error_buffer) > 8192:
                        error_buffer = error_buffer[-4096:]
                    # Check for error events before yielding to client
                    _check_stream_error(error_buffer)
                    yield chunk
                p_latency = (time.time() - p_start) * 1000
                total_latency = (time.time() - start_time) * 1000

                self.circuit_breaker.record_success(provider_cfg.name)

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

                return  # 流成功完成

            except RetryableError as e:
                p_latency = (time.time() - p_start) * 1000
                self.circuit_breaker.record_failure(
                    provider_cfg.name, immediate=e.immediate_break
                )
                errors.append(
                    {
                        "provider": provider_cfg.name,
                        "model": provider_cfg.model,
                        "priority": provider_cfg.priority,
                        "error": str(e),
                        "retryable": True,
                    }
                )
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
                    "provider.fail",
                    request_id=request_id,
                    provider=provider_cfg.name,
                    model=provider_cfg.model,
                    error=str(e),
                    retry=True,
                    provider_latency_ms=round(p_latency),
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
                        reason="retryable_error",
                        circuit_broken=e.immediate_break,
                    )

            except NonRetryableError as e:
                p_latency = (time.time() - p_start) * 1000
                errors.append(
                    {
                        "provider": provider_cfg.name,
                        "model": provider_cfg.model,
                        "priority": provider_cfg.priority,
                        "error": str(e),
                        "retryable": False,
                        "latency_ms": round(p_latency),
                    }
                )
                logger.error(
                    "provider.fail",
                    request_id=request_id,
                    provider=provider_cfg.name,
                    model=provider_cfg.model,
                    error=str(e),
                    retry=False,
                    provider_latency_ms=round(p_latency),
                )
                if outcome is not None:
                    outcome["provider_name"] = provider_cfg.name
                    outcome["provider_type"] = provider_cfg.type
                    outcome["provider_model"] = provider_cfg.model
                    outcome["provider_url"] = provider_cfg.base_url
                    outcome["attempt"] = attempt
                raise

        # 全部失败
        total_latency = (time.time() - start_time) * 1000
        logger.error(
            "failover.exhausted",
            request_id=request_id,
            model=virtual_model,
            attempts=len(providers),
            total_latency_ms=round(total_latency),
            errors=errors,
        )
        raise AllProvidersFailedError(virtual_model, errors)

    def _get_providers(self, virtual_model: str) -> list[ProviderConfig]:
        if virtual_model not in self.config.models:
            raise UnknownModelError(virtual_model, list(self.config.models.keys()))

        all_providers = self.config.models[virtual_model]
        available: list[ProviderConfig] = []
        skipped: list[dict] = []

        for p in all_providers:
            if self.circuit_breaker.is_available(p.name):
                available.append(p)
            else:
                skipped.append(
                    {"provider": p.name, "model": p.model, "state": self.circuit_breaker.state(p.name).value}
                )

        if skipped:
            logger.info(
                "circuit.providers_skipped",
                model=virtual_model,
                skipped=skipped,
                available_count=len(available),
            )

        if not available and skipped:
            raise AllProvidersFailedError(
                virtual_model,
                [
                    {
                        "provider": s["provider"],
                        "model": s["model"],
                        "error": f"provider 已熔断 (state={s['state']})",
                        "retryable": True,
                    }
                    for s in skipped
                ],
            )

        return available

    @property
    def model_names(self) -> list[str]:
        return list(self.config.models.keys())


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
