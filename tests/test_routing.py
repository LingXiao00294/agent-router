from __future__ import annotations

import pytest
from agent_router.routing import Router, UnknownModelError, AllProvidersFailedError


class TestRouterModelLookup:
    def test_known_model(self, sample_config, http_client):
        router = Router(sample_config, http_client)
        providers = router._get_providers("haiku-router")
        assert len(providers) == 2
        assert providers[0].model == "claude-haiku-4-5-20251001"

    def test_unknown_model(self, sample_config, http_client):
        router = Router(sample_config, http_client)
        with pytest.raises(UnknownModelError) as exc:
            router._get_providers("nonexistent-router")
        assert "nonexistent-router" in str(exc.value)
        assert "haiku-router" in exc.value.known

    def test_model_names(self, sample_config, http_client):
        router = Router(sample_config, http_client)
        names = router.model_names
        assert "haiku-router" in names
        assert "sonnet-router" in names


class TestAllProvidersFailedError:
    def test_formatting(self):
        errors = [
            {"provider": "anthropic", "model": "m1", "error": "HTTP 429"},
            {"provider": "anthropic", "model": "m2", "error": "timeout"},
        ]
        exc = AllProvidersFailedError("test-model", errors)
        msg = str(exc)
        assert "test-model" in msg
        assert "HTTP 429" in msg
        assert "timeout" in msg
