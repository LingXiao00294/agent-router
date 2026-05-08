from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator

import structlog

from agent_router.circuit_breaker import CircuitBreaker
from agent_router.config import AppConfig, ProviderConfig
from agent_router.providers.anthropic_compat import AnthropicCompatProvider
from agent_router.providers.base import BaseProvider, NonRetryableError, RetryableError

logger = structlog.get_logger(__name__)


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
        self.circuit_breaker = CircuitBreaker()

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
            provider = _create_provider(provider_cfg, self.http)
            attempt = i + 1

            logger.info(
                "provider.try",
                request_id=request_id,
                provider=provider_cfg.type,
                model=provider_cfg.model,
                priority=provider_cfg.priority,
                attempt=attempt,
            )

            try:
                p_start = time.time()
                result = await provider.send(request_body)
                p_latency = (time.time() - p_start) * 1000
                total_latency = (time.time() - start_time) * 1000

                self.circuit_breaker.record_success(provider_cfg.name)

                logger.info(
                    "provider.success",
                    request_id=request_id,
                    provider=provider_cfg.type,
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
                # 不重试错误立即返回
                total_latency = (time.time() - start_time) * 1000
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
            provider = _create_provider(provider_cfg, self.http)
            attempt = i + 1

            logger.info(
                "provider.try",
                request_id=request_id,
                provider=provider_cfg.type,
                model=provider_cfg.model,
                priority=provider_cfg.priority,
                attempt=attempt,
            )

            try:
                p_start = time.time()
                async for chunk in provider.send_stream(request_body):
                    yield chunk
                p_latency = (time.time() - p_start) * 1000
                total_latency = (time.time() - start_time) * 1000

                self.circuit_breaker.record_success(provider_cfg.name)

                logger.info(
                    "provider.success",
                    request_id=request_id,
                    provider=provider_cfg.type,
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
                total_latency = (time.time() - start_time) * 1000
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
