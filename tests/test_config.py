from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from agent_router.app import create_app
from agent_router.config import (
    AppConfig,
    ProviderConfig,
    VirtualModelConfig,
    load_config,
)
from agent_router.db import CallStore
from agent_router.routing import Router


def _write_toml(content: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False)
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


class TestLoadConfig:
    def test_basic_config(self):
        toml = """
[server]
host = "0.0.0.0"
port = 9999

[providers.p1]
type = "anthropic"
api_key = "sk-test"
base_url = "https://test.api.com"

[[models.test]]
provider = "p1"
model = "claude-test"
priority = 1
"""
        path = _write_toml(toml)
        try:
            config = load_config(path)
            assert config.server.host == "0.0.0.0"
            assert config.server.port == 9999
            assert "test" in config.models
            assert len(config.models["test"].providers) == 1
            assert config.models["test"].providers[0].model == "claude-test"
            assert config.models["test"].providers[0].api_key == "sk-test"
        finally:
            path.unlink()

    def test_failover_allows_stale_pins(self):
        """failover 模式下过期 pin 不阻止加载（sticky 才校验链成员）."""
        toml = """
[server]
host = "127.0.0.1"
port = 9456

[router]
mode = "failover"

[providers.p1]
type = "anthropic"
api_key = "k"
base_url = "https://api.com"

[models.test]
pinned_provider = "gone"
pinned_model = "old"

[[models.test.providers]]
provider = "p1"
model = "m1"
priority = 1
"""
        path = _write_toml(toml)
        try:
            config = load_config(path)
            assert config.models["test"].pinned_provider == "gone"
            assert config.models["test"].pinned_model == "old"
        finally:
            path.unlink()

    def test_sticky_rejects_stale_pins(self, capsys):
        toml = """
[server]
host = "127.0.0.1"
port = 9456

[router]
mode = "sticky"

[providers.p1]
type = "anthropic"
api_key = "k"
base_url = "https://api.com"

[models.test]
pinned_provider = "gone"
pinned_model = "old"

[[models.test.providers]]
provider = "p1"
model = "m1"
priority = 1
"""
        path = _write_toml(toml)
        try:
            with pytest.raises(SystemExit):
                load_config(path)
            assert "不在该虚拟模型的 provider 链中" in capsys.readouterr().err
        finally:
            path.unlink()

    def test_priority_sorting(self):
        toml = """
[server]
host = "127.0.0.1"
port = 9456

[providers.p1]
type = "anthropic"
api_key = "k"
base_url = "https://api.com"

[[models.test]]
provider = "p1"
model = "third"
priority = 3

[[models.test]]
provider = "p1"
model = "first"
priority = 1

[[models.test]]
provider = "p1"
model = "second"
priority = 2
"""
        path = _write_toml(toml)
        try:
            config = load_config(path)
            providers = config.models["test"].providers
            assert [p.priority for p in providers] == [1, 2, 3]
            assert [p.model for p in providers] == ["first", "second", "third"]
        finally:
            path.unlink()

    def test_env_var_interpolation(self):
        os.environ["TEST_API_KEY"] = "env-key-123"
        toml = """
[server]
host = "127.0.0.1"
port = 9456

[providers.p1]
type = "anthropic"
api_key = "${TEST_API_KEY}"
base_url = "https://api.com"

[[models.test]]
provider = "p1"
model = "m1"
priority = 1
"""
        path = _write_toml(toml)
        try:
            config = load_config(path)
            assert config.models["test"].providers[0].api_key == "env-key-123"
        finally:
            path.unlink()
            del os.environ["TEST_API_KEY"]

    def test_missing_config_file(self):
        with pytest.raises(SystemExit):
            load_config("/nonexistent/config.toml")

    def test_empty_models(self):
        toml = """
[server]
host = "127.0.0.1"
port = 9456

[providers.p1]
type = "anthropic"
api_key = "k"
base_url = "https://api.com"
"""
        path = _write_toml(toml)
        try:
            config = load_config(path)
            assert config.models == {}
        finally:
            path.unlink()

    def test_empty_providers(self):
        toml = """
[server]
host = "127.0.0.1"
port = 9456

[[models.test]]
provider = "p1"
model = "m1"
priority = 1
"""
        path = _write_toml(toml)
        try:
            config = load_config(path)
            assert config.models == {}
        finally:
            path.unlink()

    def test_server_only_config(self):
        toml = """
[server]
host = "127.0.0.1"
port = 9456
"""
        path = _write_toml(toml)
        try:
            config = load_config(path)
            assert config.server.host == "127.0.0.1"
            assert config.server.port == 9456
            assert config.models == {}
        finally:
            path.unlink()

    def test_unresolved_env_var(self):
        toml = """
[server]
host = "127.0.0.1"
port = 9456

[providers.p1]
type = "anthropic"
api_key = "${NONEXISTENT_ENV_VAR_12345}"
base_url = "https://api.com"

[[models.test]]
provider = "p1"
model = "m1"
priority = 1
"""
        path = _write_toml(toml)
        try:
            with pytest.raises(SystemExit):
                load_config(path)
        finally:
            path.unlink()

    def test_unresolved_env_var_allowed_for_runtime_startup(self):
        toml = """
[server]
host = "127.0.0.1"
port = 9456

[providers.p1]
type = "anthropic"
api_key = "${NONEXISTENT_ENV_VAR_12345}"
base_url = "https://api.com"

[[models.test]]
provider = "p1"
model = "m1"
priority = 1
"""
        path = _write_toml(toml)
        try:
            config = load_config(path, allow_unresolved_api_keys=True)
            assert (
                config.models["test"].providers[0].api_key
                == "${NONEXISTENT_ENV_VAR_12345}"
            )
        finally:
            path.unlink()

    def test_multiple_virtual_models(self):
        toml = """
[server]
host = "127.0.0.1"
port = 9456

[providers.p1]
type = "anthropic"
api_key = "k1"
base_url = "https://a.com"

[providers.p2]
type = "anthropic"
api_key = "k2"
base_url = "https://b.com"

[[models.haiku]]
provider = "p1"
model = "h1"
priority = 1

[[models.sonnet]]
provider = "p2"
model = "s1"
priority = 1

[[models.opus]]
provider = "p1"
model = "o1"
priority = 1
"""
        path = _write_toml(toml)
        try:
            config = load_config(path)
            assert set(config.models.keys()) == {"haiku", "sonnet", "opus"}
        finally:
            path.unlink()

    def test_unknown_provider_ref(self):
        toml = """
[server]
host = "127.0.0.1"
port = 9456

[providers.p1]
type = "anthropic"
api_key = "k"
base_url = "https://api.com"

[[models.test]]
provider = "nonexistent"
model = "m1"
priority = 1
"""
        path = _write_toml(toml)
        try:
            config = load_config(path)
            # 未知 provider 被自动跳过，模型为空不应报错
            assert "test" not in config.models
        finally:
            path.unlink()

    def test_multiple_providers_in_model(self):
        toml = """
[server]
host = "127.0.0.1"
port = 9456

[providers.anthropic]
type = "anthropic"
api_key = "sk-ant-xxx"
base_url = "https://api.anthropic.com"

[providers.zhipu]
type = "anthropic"
api_key = "glm-key"
base_url = "https://api.z.ai/api/anthropic"

[[models.haiku-router]]
provider = "anthropic"
model = "claude-haiku-4-5"
priority = 1

[[models.haiku-router]]
provider = "zhipu"
model = "glm-5.1"
priority = 2
"""
        path = _write_toml(toml)
        try:
            config = load_config(path)
            providers = config.models["haiku-router"].providers
            assert len(providers) == 2
            assert providers[0].model == "claude-haiku-4-5"
            assert providers[0].api_key == "sk-ant-xxx"
            assert providers[1].model == "glm-5.1"
            assert providers[1].api_key == "glm-key"
        finally:
            path.unlink()

    def test_missing_provider_field_in_model_ref(self):
        toml = """
[server]
host = "127.0.0.1"
port = 9456

[providers.p1]
type = "anthropic"
api_key = "k"
base_url = "https://api.com"

[[models.test]]
model = "m1"
priority = 1
"""
        path = _write_toml(toml)
        try:
            with pytest.raises(SystemExit):
                load_config(path)
        finally:
            path.unlink()


class TestReloadConfig:
    """Router.reload_config 单元测试."""

    @pytest.mark.asyncio
    async def test_reload_updates_models(self, sample_config, http_client):
        router = Router(sample_config, http_client)
        assert set(router.model_names) == {"haiku-router", "sonnet-router"}

        new_config = AppConfig(
            server=sample_config.server,
            models={
                "new-model": VirtualModelConfig(
                    providers=[
                        ProviderConfig(
                            type="anthropic",
                            name="p1",
                            model="m-new",
                            api_key="k",
                            base_url="https://api.com",
                            priority=1,
                        ),
                    ]
                ),
            },
        )
        await router.reload_config(new_config)
        assert router.model_names == ["new-model"]
        assert router.config.models["new-model"].providers[0].model == "m-new"

    @pytest.mark.asyncio
    async def test_reload_preserves_circuit_breaker(self, sample_config, http_client):
        router = Router(sample_config, http_client)
        # 触发一个熔断
        await router.circuit_breaker.record_failure("anthropic", immediate=True)
        state = await router.circuit_breaker.state("anthropic")
        assert state.value == "open"

        new_config = AppConfig(
            server=sample_config.server,
            models={
                "m": VirtualModelConfig(
                    providers=[
                        ProviderConfig(
                            type="anthropic",
                            name="anthropic",
                            model="x",
                            api_key="k",
                            base_url="https://api.com",
                            priority=1,
                        )
                    ]
                )
            },
        )
        await router.reload_config(new_config)

        # 熔断状态保留
        state = await router.circuit_breaker.state("anthropic")
        assert state.value == "open"


_TOML_TEMPLATE = """\
[server]
host = "127.0.0.1"
port = 9456

[providers.p1]
type = "anthropic"
api_key = "sk-test"
base_url = "https://api.anthropic.com"

[[models.{model_name}]]
provider = "p1"
model = "{model_name}"
priority = 1
"""


class TestHotReloadAPI:
    """PUT /api/config 热重载集成测试."""

    @pytest.fixture
    async def store(self):
        s = CallStore(":memory:")
        await s.init()
        yield s
        await s.close()

    @pytest.mark.asyncio
    async def test_put_config_hot_reload(self, store):
        """PUT 后 /v1/models 应立即返回新模型，无需重启."""
        path = _write_toml(_TOML_TEMPLATE.format(model_name="old-model"))
        try:
            config = load_config(path)
            app = create_app(config, store, config_path=str(path))
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                # 确认初始模型
                resp = await ac.get("/v1/models")
                assert resp.json()["data"][0]["id"] == "old-model"

                # PUT 新配置
                new_body = {
                    "server": {"host": "127.0.0.1", "port": 9456},
                    "providers": {
                        "p1": {
                            "type": "anthropic",
                            "api_key": "sk-test",
                            "base_url": "https://api.anthropic.com",
                        },
                    },
                    "models": {
                        "new-model": [
                            {"provider": "p1", "model": "new-model", "priority": 1},
                        ],
                    },
                }
                resp = await ac.put("/api/config", json=new_body)
                assert resp.status_code == 200
                assert resp.json()["message"] == "配置已更新并热重载"

                # 热重载后模型应已变化
                resp = await ac.get("/v1/models")
                assert resp.json()["data"][0]["id"] == "new-model"
        finally:
            path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_switch_to_sticky_without_pin_is_rejected_before_write(self, store):
        """缺少模型 pin 时切换 sticky 应返回 400，且不得改写配置文件."""
        original = """\
[server]
host = "127.0.0.1"
port = 9456

[router]
mode = "failover"

[providers.p1]
type = "anthropic"
api_key = "sk-test"
base_url = "https://api.anthropic.com"

[[models.unpinned]]
provider = "p1"
model = "m1"
priority = 1
"""
        path = _write_toml(original)
        try:
            config = load_config(path)
            app = create_app(config, store, config_path=str(path))
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.put(
                    "/api/config",
                    json={"router": {"mode": "sticky"}},
                )

            assert resp.status_code == 400
            assert "模型 'unpinned' 未指定 pin" in resp.json()["detail"]
            assert path.read_text() == original
            assert app.state.router_engine.config.router.mode == "failover"
        finally:
            path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_switch_to_sticky_with_valid_pin_succeeds(self, store):
        """每个模型都有有效 pin 时应允许切换 sticky."""
        toml = """\
[server]
host = "127.0.0.1"
port = 9456

[router]
mode = "failover"

[providers.p1]
type = "anthropic"
api_key = "sk-test"
base_url = "https://api.anthropic.com"

[models.pinned]
pinned_provider = "p1"
pinned_model = "m1"

[[models.pinned.providers]]
provider = "p1"
model = "m1"
priority = 1
"""
        path = _write_toml(toml)
        try:
            config = load_config(path)
            app = create_app(config, store, config_path=str(path))
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.put(
                    "/api/config",
                    json={"router": {"mode": "sticky"}},
                )

            assert resp.status_code == 200
            assert load_config(path).router.mode == "sticky"
            assert app.state.router_engine.config.router.mode == "sticky"
        finally:
            path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_get_config_marks_unresolved_api_key_as_missing(
        self, store, monkeypatch
    ):
        """未设置的环境变量占位符应允许页面直接填写 key."""
        monkeypatch.delenv("NONEXISTENT_ENV_VAR_12345", raising=False)
        toml = """\
[server]
host = "127.0.0.1"
port = 9456

[providers.p1]
type = "anthropic"
api_key = "${NONEXISTENT_ENV_VAR_12345}"
base_url = "https://api.anthropic.com"

[[models.m1]]
provider = "p1"
model = "m1"
priority = 1
"""
        path = _write_toml(toml)
        try:
            config = load_config(path, allow_unresolved_api_keys=True)
            app = create_app(config, store, config_path=str(path))
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/config")
                assert resp.status_code == 200
                provider = resp.json()["providers"]["p1"]
                assert provider["api_key"] == ""
                assert provider["has_key"] is False
                assert provider["api_key_unresolved"] is True
        finally:
            path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_put_config_priority_change(self, store):
        """修改优先级后热重载生效."""
        toml = """\
[server]
host = "127.0.0.1"
port = 9456

[providers.p1]
type = "anthropic"
api_key = "sk-test"
base_url = "https://api.anthropic.com"

[providers.p2]
type = "anthropic"
api_key = "sk-test2"
base_url = "https://api2.anthropic.com"

[[models.mymodel]]
provider = "p1"
model = "model-a"
priority = 1

[[models.mymodel]]
provider = "p2"
model = "model-b"
priority = 2
"""
        path = _write_toml(toml)
        try:
            config = load_config(path)
            app = create_app(config, store, config_path=str(path))
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                # 初始: p1 优先
                resp = await ac.get("/api/config/models")
                models = resp.json()
                assert models["mymodel"]["providers"][0]["provider"] == "p1"

                # 交换优先级
                new_body = {
                    "server": {"host": "127.0.0.1", "port": 9456},
                    "providers": {
                        "p1": {
                            "type": "anthropic",
                            "api_key": "sk-test",
                            "base_url": "https://api.anthropic.com",
                        },
                        "p2": {
                            "type": "anthropic",
                            "api_key": "sk-test2",
                            "base_url": "https://api2.anthropic.com",
                        },
                    },
                    "models": {
                        "mymodel": {
                            "providers": [
                                {"provider": "p2", "model": "model-b", "priority": 1},
                                {"provider": "p1", "model": "model-a", "priority": 2},
                            ],
                        },
                    },
                }
                resp = await ac.put("/api/config", json=new_body)
                assert resp.status_code == 200

                # 热重载后优先级已变化
                resp = await ac.get("/api/config/models")
                models = resp.json()
                assert models["mymodel"]["providers"][0]["provider"] == "p2"
        finally:
            path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_put_missing_models_preserves_existing(self, store):
        """PUT body 缺少 models 时应保留已有模型配置."""
        path = _write_toml(_TOML_TEMPLATE.format(model_name="keep-me"))
        try:
            config = load_config(path)
            app = create_app(config, store, config_path=str(path))
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                # body 不含 models
                body = {
                    "server": {"host": "127.0.0.1", "port": 9456},
                    "providers": {
                        "p1": {
                            "type": "anthropic",
                            "api_key": "sk-test",
                            "base_url": "https://api.anthropic.com",
                        },
                    },
                }
                resp = await ac.put("/api/config", json=body)
                assert resp.status_code == 200

                # 模型应保留
                resp = await ac.get("/v1/models")
                data = resp.json()["data"]
                assert len(data) == 1
                assert data[0]["id"] == "keep-me"
        finally:
            path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_put_missing_router_preserves_existing(self, store):
        """PUT body 缺少 router 时应保留已有 router 配置."""
        toml = """\
[server]
host = "127.0.0.1"
port = 9456

[router]
failure_threshold = 10
recovery_timeout = 300.0

[providers.p1]
type = "anthropic"
api_key = "sk-test"
base_url = "https://api.anthropic.com"

[[models.m1]]
provider = "p1"
model = "m1"
priority = 1
"""
        path = _write_toml(toml)
        try:
            config = load_config(path)
            app = create_app(config, store, config_path=str(path))
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                # body 不含 router
                body = {
                    "server": {"host": "127.0.0.1", "port": 9456},
                    "providers": {
                        "p1": {
                            "type": "anthropic",
                            "api_key": "sk-test",
                            "base_url": "https://api.anthropic.com",
                        },
                    },
                    "models": {
                        "m1": [{"provider": "p1", "model": "m1", "priority": 1}],
                    },
                }
                resp = await ac.put("/api/config", json=body)
                assert resp.status_code == 200

                # 验证 router 段保留
                resp = await ac.get("/api/config")
                cfg = resp.json()
                assert cfg["router"]["failure_threshold"] == 10
                assert cfg["router"]["recovery_timeout"] == 300.0
        finally:
            path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_put_new_provider_with_masked_key_rejected(self, store):
        """新建 provider 用脱敏 api_key 应返回 400."""
        path = _write_toml(_TOML_TEMPLATE.format(model_name="m1"))
        try:
            config = load_config(path)
            app = create_app(config, store, config_path=str(path))
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                body = {
                    "server": {"host": "127.0.0.1", "port": 9456},
                    "providers": {
                        "p1": {
                            "type": "anthropic",
                            "api_key": "sk-test",
                            "base_url": "https://api.anthropic.com",
                        },
                        "new-provider": {
                            "type": "anthropic",
                            "api_key": "sk-a****-xy",  # 脱敏值
                            "base_url": "https://new.api.com",
                        },
                    },
                    "models": {
                        "m1": [{"provider": "p1", "model": "m1", "priority": 1}],
                    },
                }
                resp = await ac.put("/api/config", json=body)
                assert resp.status_code == 400
                assert "new-provider" in resp.json()["detail"]
        finally:
            path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_reload_updates_circuit_breaker_thresholds(self, store):
        """热重载后熔断器阈值应同步更新."""
        toml = """\
[server]
host = "127.0.0.1"
port = 9456

[router]
failure_threshold = 5
recovery_timeout = 600.0

[providers.p1]
type = "anthropic"
api_key = "sk-test"
base_url = "https://api.anthropic.com"

[[models.m1]]
provider = "p1"
model = "m1"
priority = 1
"""
        path = _write_toml(toml)
        try:
            config = load_config(path)
            app = create_app(config, store, config_path=str(path))
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                # 修改 router 阈值
                body = {
                    "server": {"host": "127.0.0.1", "port": 9456},
                    "router": {
                        "failure_threshold": 3,
                        "recovery_timeout": 120.0,
                    },
                    "providers": {
                        "p1": {
                            "type": "anthropic",
                            "api_key": "sk-test",
                            "base_url": "https://api.anthropic.com",
                        },
                    },
                    "models": {
                        "m1": [{"provider": "p1", "model": "m1", "priority": 1}],
                    },
                }
                resp = await ac.put("/api/config", json=body)
                assert resp.status_code == 200

                # 重新加载配置验证阈值已更新
                new_config = load_config(path)
                assert new_config.router.failure_threshold == 3
                assert new_config.router.recovery_timeout == 120.0
        finally:
            path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_put_config_skips_empty_model_tables(self, store):
        """空 providers 的模型不应写出裸 [models.x]，以免热重载失败."""
        path = _write_toml(_TOML_TEMPLATE.format(model_name="keep-me"))
        try:
            config = load_config(path)
            app = create_app(config, store, config_path=str(path))
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                body = {
                    "server": {"host": "127.0.0.1", "port": 9456},
                    "providers": {
                        "p1": {
                            "type": "anthropic",
                            "api_key": "sk-test",
                            "base_url": "https://api.anthropic.com",
                        },
                    },
                    "models": {
                        "keep-me": [
                            {"provider": "p1", "model": "keep-me", "priority": 1},
                        ],
                        "gone": {"providers": []},
                        "also-gone": [],
                    },
                }
                resp = await ac.put("/api/config", json=body)
                assert resp.status_code == 200

                written = path.read_text()
                assert "[models.gone]" not in written
                assert "[models.also-gone]" not in written
                assert "[models.keep-me]" in written

                models = (await ac.get("/v1/models")).json()["data"]
                ids = {m["id"] for m in models}
                assert ids == {"keep-me"}
        finally:
            path.unlink(missing_ok=True)
