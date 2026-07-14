from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tomllib

import pytest
from httpx import ASGITransport, AsyncClient

from agent_router import app as app_module
from agent_router.api import config as config_api
from agent_router.app import create_app
from agent_router.config import (
    ActualModelDef,
    AppConfig,
    ConfigError,
    ModelRef,
    ProviderConfig,
    RouterConfig,
    ServerConfig,
    VirtualModelConfig,
    load_config,
    parse_config_data,
)
from agent_router.db import CallStore
from agent_router.routing import Router


BASE_TOML = """\
[server]
host = "127.0.0.1"
port = 9456

[router]
mode = "sticky"
failure_threshold = 5
recovery_timeout = 600

[providers.p1]
type = "anthropic"
api_key = "sk-provider-one"
base_url = "https://p1.test/"

[providers.p1.models.shared]
input_price_per_million = 1.0
output_price_per_million = 4.0
cache_read_price_per_million = 0.1
cache_write_price_per_million = 1.25

[providers.p1.models.other]

[providers.p2]
type = "anthropic"
api_key = "sk-provider-two"
base_url = "https://p2.test"

[providers.p2.models.shared]

[models.router]
pinned_model = { provider = "p1", model = "shared" }
models = [
  { provider = "p1", model = "shared" },
  { provider = "p2", model = "shared" },
]
"""


def _write_config(tmp_path: Path, content: str = BASE_TOML) -> Path:
    """Write a TOML fixture and return its path."""
    path = tmp_path / "config.toml"
    path.write_text(content, encoding="utf-8")
    return path


def _raw_config() -> dict:
    """Return a fresh parsed copy of the canonical test configuration."""
    return tomllib.loads(BASE_TOML)


def _assert_no_temp_file(path: Path) -> None:
    assert not path.with_suffix(path.suffix + ".tmp").exists()


@pytest.fixture
async def store(tmp_path):
    """Provide an initialized isolated call store for config API tests."""
    call_store = CallStore(str(tmp_path / "calls.db"))
    await call_store.init()
    try:
        yield call_store
    finally:
        await call_store.close()


class TestConfigDomainModel:
    def test_loads_provider_catalog_and_resolves_runtime_chain(self, tmp_path):
        config = load_config(_write_config(tmp_path))

        assert set(config.providers["p1"].models) == {"shared", "other"}
        assert config.providers["p1"].base_url == "https://p1.test"
        providers = config.models["router"].providers
        assert [(item.name, item.model, item.priority) for item in providers] == [
            ("p1", "shared", 1),
            ("p2", "shared", 2),
        ]
        assert providers[0].input_price_per_million == 1.0
        assert providers[0].cache_write_price_per_million == 1.25
        assert providers[1].input_price_per_million is None
        assert config.models["router"].pinned_model == ModelRef(
            provider="p1", model="shared"
        )

    def test_array_order_generates_priority(self, tmp_path):
        raw = _raw_config()
        raw["router"]["mode"] = "failover"
        raw["models"]["router"]["models"].reverse()
        raw["models"]["router"]["pinned_model"] = None

        config = parse_config_data(raw)

        assert [provider.name for provider in config.models["router"].providers] == [
            "p2",
            "p1",
        ]
        assert [
            provider.priority for provider in config.models["router"].providers
        ] == [
            1,
            2,
        ]

    def test_multiple_virtual_models_can_share_actual_model(self):
        raw = _raw_config()
        raw["models"]["second"] = {
            "pinned_model": {"provider": "p1", "model": "shared"},
            "models": [{"provider": "p1", "model": "shared"}],
        }

        config = parse_config_data(raw)

        assert config.models["router"].providers[0].model == "shared"
        assert config.models["second"].providers[0].model == "shared"

    def test_missing_and_explicit_zero_prices_remain_distinct(self):
        raw = _raw_config()
        raw["providers"]["p1"]["models"]["other"] = {
            "input_price_per_million": 0,
            "output_price_per_million": 0,
            "cache_read_price_per_million": 0,
            "cache_write_price_per_million": 0,
        }
        raw["router"]["mode"] = "failover"
        raw["models"]["router"] = {
            "models": [
                {"provider": "p2", "model": "shared"},
                {"provider": "p1", "model": "other"},
            ]
        }

        config = parse_config_data(raw)
        missing, zero = config.models["router"].providers

        assert missing.input_price_per_million is None
        assert zero.input_price_per_million == 0.0

    @pytest.mark.parametrize(
        ("mutate", "message"),
        [
            (
                lambda raw: raw["models"]["router"]["models"].append(
                    {"provider": "missing", "model": "shared"}
                ),
                "未知 Provider",
            ),
            (
                lambda raw: raw["models"]["router"]["models"].append(
                    {"provider": "p1", "model": "missing"}
                ),
                "未在 Provider",
            ),
            (
                lambda raw: raw["models"]["router"]["models"].append(
                    {"provider": "p1", "model": "shared"}
                ),
                "不能重复引用",
            ),
        ],
    )
    def test_rejects_invalid_model_references(self, mutate, message):
        raw = _raw_config()
        mutate(raw)

        with pytest.raises(ConfigError, match=message):
            parse_config_data(raw)

    def test_rejects_blank_actual_model_name(self):
        raw = _raw_config()
        raw["providers"]["p1"]["models"][""] = {}

        with pytest.raises(ConfigError, match="实际模型名不能为空"):
            parse_config_data(raw)

    @pytest.mark.parametrize(
        "price", [-0.01, float("-inf"), float("inf"), float("nan")]
    )
    def test_rejects_non_finite_or_negative_actual_model_price(self, price):
        raw = _raw_config()
        raw["providers"]["p1"]["models"]["shared"]["input_price_per_million"] = price

        with pytest.raises(ConfigError, match="模型费用必须大于等于 0"):
            parse_config_data(raw)

    def test_allows_empty_provider_catalog(self):
        raw = _raw_config()
        raw["providers"]["empty"] = {
            "type": "anthropic",
            "api_key": "sk-empty",
            "base_url": "https://empty.test",
            "models": {},
        }

        config = parse_config_data(raw)

        assert config.providers["empty"].models == {}

    def test_rejects_empty_virtual_model_chain(self):
        raw = _raw_config()
        raw["models"]["router"]["models"] = []

        with pytest.raises(ConfigError, match="at least 1 item"):
            parse_config_data(raw)

    def test_sticky_requires_structured_pin_in_chain(self):
        missing = _raw_config()
        missing["models"]["router"]["pinned_model"] = None
        stale = _raw_config()
        stale["models"]["router"]["pinned_model"] = {
            "provider": "p1",
            "model": "other",
        }

        with pytest.raises(ConfigError, match="必须设置 pinned_model"):
            parse_config_data(missing)
        with pytest.raises(ConfigError, match="不在该虚拟模型的模型链中"):
            parse_config_data(stale)

    def test_rejects_unknown_fields_and_legacy_format(self):
        unknown = _raw_config()
        unknown["models"]["router"]["priority"] = 1
        legacy = _raw_config()
        legacy["models"]["router"] = {
            "pinned_provider": "p1",
            "pinned_model": "shared",
            "providers": [{"provider": "p1", "model": "shared", "priority": 1}],
        }

        with pytest.raises(ConfigError, match="旧版配置格式"):
            parse_config_data(unknown)
        with pytest.raises(ConfigError, match="旧版配置格式"):
            parse_config_data(legacy)

        string_pin = _raw_config()
        string_pin["models"]["router"]["pinned_model"] = "shared"
        with pytest.raises(ConfigError, match="旧版配置格式"):
            parse_config_data(string_pin)

    def test_unresolved_api_key_is_strict_by_default(self, tmp_path, monkeypatch):
        monkeypatch.delenv("MISSING_PROVIDER_KEY", raising=False)
        raw = _raw_config()
        raw["providers"]["p1"]["api_key"] = "${MISSING_PROVIDER_KEY}"
        path = _write_config(tmp_path, config_api._serialize_toml(raw))

        with pytest.raises(ConfigError, match="环境变量未设置"):
            load_config(path)

        config = load_config(path, allow_unresolved_api_keys=True)
        assert config.providers["p1"].api_key == "${MISSING_PROVIDER_KEY}"

    def test_missing_file_raises_structured_error(self, tmp_path):
        with pytest.raises(ConfigError, match="配置文件不存在"):
            load_config(tmp_path / "missing.toml")


class TestRuntimeReload:
    async def test_reload_updates_config_and_provider_limits(self, sample_config):
        router = Router(sample_config, http_client=None)
        new_config = AppConfig(
            server=ServerConfig(),
            router=RouterConfig(
                mode="failover", failure_threshold=2, recovery_timeout=30
            ),
            models={
                "new-model": VirtualModelConfig(
                    providers=[
                        ProviderConfig(
                            type="anthropic",
                            name="new-provider",
                            model="new-actual",
                            api_key="sk-new",
                            base_url="https://new.test",
                            priority=1,
                            max_concurrent=3,
                        )
                    ]
                )
            },
        )

        await router.reload_config(new_config)

        assert router.model_names == ["new-model"]
        assert router.circuit_breaker.failure_threshold == 2
        assert router.provider_gate.snapshot()["new-provider"]["max_concurrent"] == 3

    async def test_reload_failure_restores_old_runtime(
        self, sample_config, monkeypatch
    ):
        router = Router(sample_config, http_client=None)
        old_config = router.config
        new_config = old_config.model_copy(deep=True)
        new_config.router.failure_threshold = 1
        original_configure = router.provider_gate.configure_from_models
        calls = 0

        def fail_once(models):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("gate failed")
            original_configure(models)

        monkeypatch.setattr(router.provider_gate, "configure_from_models", fail_once)

        with pytest.raises(RuntimeError, match="gate failed"):
            await router.reload_config(new_config)

        assert router.config is old_config
        assert (
            router.circuit_breaker.failure_threshold
            == old_config.router.failure_threshold
        )


class TestConfigApi:
    async def _client(self, path: Path, store):
        config = load_config(path)
        app = create_app(config, store, config_path=str(path))
        return app, AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        )

    async def test_get_endpoints_return_canonical_catalog(self, tmp_path, store):
        path = _write_config(tmp_path)
        _, client = await self._client(path, store)
        async with client:
            full = (await client.get("/api/config")).json()
            providers = (await client.get("/api/config/providers")).json()
            models = (await client.get("/api/config/models")).json()

        assert full["providers"]["p1"]["api_key"] != "sk-provider-one"
        assert set(providers["p1"]["models"]) == {"shared", "other"}
        assert models["router"]["pinned_model"] == {
            "provider": "p1",
            "model": "shared",
        }
        assert models["router"]["models"][1] == {
            "provider": "p2",
            "model": "shared",
        }

    def test_toml_serializer_escapes_all_control_characters(self):
        raw = _raw_config()
        api_key = "key\b\t\n\f\r\x00\x1f\x7f"
        raw["providers"]["p1"]["api_key"] = api_key

        parsed = tomllib.loads(config_api._serialize_toml(raw))

        assert parsed["providers"]["p1"]["api_key"] == api_key

    async def test_malformed_provider_returns_actionable_400(self, tmp_path, store):
        path = _write_config(tmp_path)
        _, client = await self._client(path, store)
        path.write_text('providers = { p1 = "invalid" }\n', encoding="utf-8")

        async with client:
            get_response = await client.get("/api/config")
            put_response = await client.put("/api/config", json=_raw_config())

        assert get_response.status_code == 400
        assert "Provider 'p1' 配置必须是对象" in get_response.text
        assert put_response.status_code == 400
        assert "现有 Provider 'p1' 配置必须是对象" in put_response.text

    async def test_put_writes_only_new_format_and_preserves_masked_key(
        self, tmp_path, store
    ):
        path = _write_config(tmp_path)
        app, client = await self._client(path, store)
        body = _raw_config()
        body["providers"]["p1"]["api_key"] = "sk-p**********-one"
        body["router"]["mode"] = "failover"
        body["models"]["router"]["pinned_model"] = None
        body["models"]["router"]["models"].reverse()

        async with client:
            response = await client.put("/api/config", json=body)

        assert response.status_code == 200, response.text
        written = path.read_text(encoding="utf-8")
        parsed = tomllib.loads(written)
        assert "[[models.router.providers]]" not in written
        assert "priority" not in written
        assert parsed["providers"]["p1"]["api_key"] == "sk-provider-one"
        assert [
            provider.name
            for provider in app.state.router_engine.config.models["router"].providers
        ] == ["p2", "p1"]
        _assert_no_temp_file(path)

    async def test_get_payload_can_be_put_back_without_readonly_key_metadata(
        self, tmp_path, store
    ):
        path = _write_config(tmp_path)
        _, client = await self._client(path, store)

        async with client:
            body = (await client.get("/api/config")).json()
            response = await client.put("/api/config", json=body)

        assert response.status_code == 200, response.text
        providers = tomllib.loads(path.read_text(encoding="utf-8"))["providers"]
        assert providers["p1"]["api_key"] == "sk-provider-one"
        assert "has_key" not in providers["p1"]
        assert "api_key_unresolved" not in providers["p1"]

    async def test_put_rejects_unknown_reference_before_touching_file(
        self, tmp_path, store, monkeypatch
    ):
        path = _write_config(tmp_path)
        original = path.read_bytes()
        app, client = await self._client(path, store)
        old_runtime = app.state.router_engine.config
        logging_calls: list[dict] = []
        monkeypatch.setattr(
            app_module,
            "reconfigure_logging",
            lambda **kwargs: logging_calls.append(kwargs),
        )
        body = _raw_config()
        body["models"]["router"]["models"][0]["model"] = "missing"

        async with client:
            response = await client.put("/api/config", json=body)

        assert response.status_code == 400
        assert path.read_bytes() == original
        assert app.state.router_engine.config is old_runtime
        assert logging_calls == []
        _assert_no_temp_file(path)

    async def test_provider_deletion_conflict_has_fixed_409_contract(
        self, tmp_path, store
    ):
        path = _write_config(tmp_path)
        _, client = await self._client(path, store)
        body = _raw_config()
        del body["providers"]["p2"]

        async with client:
            response = await client.put("/api/config", json=body)

        assert response.status_code == 409
        error = response.json()["error"]
        assert error == {
            "code": "provider_in_use",
            "provider": "p2",
            "referenced_by": ["router"],
        }
        assert "model" not in error

    async def test_actual_model_deletion_conflict_has_fixed_409_contract(
        self, tmp_path, store
    ):
        path = _write_config(tmp_path)
        _, client = await self._client(path, store)
        body = _raw_config()
        del body["providers"]["p1"]["models"]["shared"]

        async with client:
            response = await client.put("/api/config", json=body)

        assert response.status_code == 409
        assert response.json() == {
            "error": {
                "code": "model_in_use",
                "provider": "p1",
                "model": "shared",
                "referenced_by": ["router"],
            }
        }

    async def test_reference_removal_must_be_saved_before_model_deletion(
        self, tmp_path, store
    ):
        path = _write_config(tmp_path)
        _, client = await self._client(path, store)
        remove_reference = _raw_config()
        remove_reference["models"]["router"]["models"] = [
            {"provider": "p2", "model": "shared"}
        ]
        remove_reference["models"]["router"]["pinned_model"] = {
            "provider": "p2",
            "model": "shared",
        }

        async with client:
            first = await client.put("/api/config", json=remove_reference)
            delete_model = deepcopy(remove_reference)
            del delete_model["providers"]["p1"]["models"]["shared"]
            second = await client.put("/api/config", json=delete_model)

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert (
            "shared" not in tomllib.loads(path.read_text())["providers"]["p1"]["models"]
        )

    async def test_put_writes_utf8_under_non_utf8_locale(
        self, tmp_path, store, monkeypatch
    ):
        """配置写回不应受 Windows 非 UTF-8 默认编码影响。"""
        import builtins

        path = _write_config(tmp_path)
        _, client = await self._client(path, store)
        body = _raw_config()
        body["providers"]["p1"]["models"]["智谱模型"] = {}
        real_open = builtins.open

        def fake_open(file, mode="r", *args, encoding=None, **kwargs):
            if encoding is None and "b" not in mode:
                encoding = "gbk"
            return real_open(file, mode, *args, encoding=encoding, **kwargs)

        monkeypatch.setattr(builtins, "open", fake_open)

        async with client:
            response = await client.put("/api/config", json=body)

        assert response.status_code == 200, response.text
        written = path.read_bytes().decode("utf-8")
        assert "智谱模型" in written
        assert '[providers.p1.models."智谱模型"]' in written

    async def test_write_failure_preserves_file_and_runtime(
        self, tmp_path, store, monkeypatch
    ):
        path = _write_config(tmp_path)
        original = path.read_bytes()
        app, client = await self._client(path, store)
        old_runtime = app.state.router_engine.config
        logging_calls: list[dict] = []

        def fail_write(path, content):
            raise OSError("disk full")

        monkeypatch.setattr(config_api, "_replace_file", fail_write)
        monkeypatch.setattr(
            app_module,
            "reconfigure_logging",
            lambda **kwargs: logging_calls.append(kwargs),
        )
        async with client:
            response = await client.put("/api/config", json=_raw_config())

        assert response.status_code == 500
        assert path.read_bytes() == original
        assert app.state.router_engine.config is old_runtime
        assert logging_calls == []
        _assert_no_temp_file(path)

    async def test_runtime_switch_failure_rolls_back_file_and_runtime(
        self, tmp_path, store, monkeypatch
    ):
        path = _write_config(tmp_path)
        original = path.read_bytes()
        app, client = await self._client(path, store)
        old_runtime = app.state.router_engine.config
        logging_calls: list[dict] = []

        async def fail_reload(config):
            raise RuntimeError("router switch failed")

        monkeypatch.setattr(app.state.router_engine, "reload_config", fail_reload)
        monkeypatch.setattr(
            app_module,
            "reconfigure_logging",
            lambda **kwargs: logging_calls.append(kwargs),
        )
        body = _raw_config()
        body["router"]["failure_threshold"] = 2
        async with client:
            response = await client.put("/api/config", json=body)

        assert response.status_code == 500
        assert path.read_bytes() == original
        assert app.state.router_engine.config is old_runtime
        assert logging_calls == []
        _assert_no_temp_file(path)

    async def test_logging_failure_rolls_back_file_router_and_logging(
        self, tmp_path, store, monkeypatch
    ):
        path = _write_config(tmp_path)
        original = path.read_bytes()
        app, client = await self._client(path, store)
        old_runtime = app.state.router_engine.config
        calls: list[dict] = []

        def fail_logging(**kwargs):
            calls.append(kwargs)
            raise RuntimeError("logging switch failed")

        monkeypatch.setattr(app_module, "reconfigure_logging", fail_logging)
        body = _raw_config()
        body["server"]["log_level"] = "debug"
        async with client:
            response = await client.put("/api/config", json=body)

        assert response.status_code == 500
        assert [call["level"] for call in calls] == ["debug"]
        assert path.read_bytes() == original
        assert app.state.router_engine.config is old_runtime
        _assert_no_temp_file(path)

    async def test_runtime_rollback_failure_preserves_original_error(
        self, tmp_path, store, monkeypatch
    ):
        path = _write_config(tmp_path)
        original = path.read_bytes()
        app, client = await self._client(path, store)
        old_runtime = app.state.router_engine.config
        logging_calls = 0

        def fail_logging_rollback(**kwargs):
            nonlocal logging_calls
            logging_calls += 1
            if logging_calls == 2:
                raise RuntimeError("logging rollback failed")

        async def fail_router_switch(config):
            raise RuntimeError("router switch failed")

        monkeypatch.setattr(app_module, "reconfigure_logging", fail_logging_rollback)
        monkeypatch.setattr(
            app.state.router_engine, "reload_config", fail_router_switch
        )
        body = _raw_config()
        body["server"]["log_level"] = "debug"
        async with client:
            response = await client.put("/api/config", json=body)

        assert response.status_code == 500
        assert "router switch failed" in response.text
        assert "logging rollback failed" in response.text
        assert "运行时回滚失败" in response.text
        assert path.read_bytes() == original
        assert app.state.router_engine.config is old_runtime
        _assert_no_temp_file(path)


def test_actual_model_definition_allows_all_prices_to_be_omitted():
    assert ActualModelDef().model_dump() == {
        "input_price_per_million": None,
        "output_price_per_million": None,
        "cache_read_price_per_million": None,
        "cache_write_price_per_million": None,
    }
