from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from agent_router.config import load_config


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
            assert len(config.models["test"]) == 1
            assert config.models["test"][0].model == "claude-test"
            assert config.models["test"][0].api_key == "sk-test"
        finally:
            path.unlink()

    def test_priority_sorting(self):
        toml = """
[server]
host = "127.0.0.1"
port = 8080

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
            providers = config.models["test"]
            assert [p.priority for p in providers] == [1, 2, 3]
            assert [p.model for p in providers] == ["first", "second", "third"]
        finally:
            path.unlink()

    def test_env_var_interpolation(self):
        os.environ["TEST_API_KEY"] = "env-key-123"
        toml = """
[server]
host = "127.0.0.1"
port = 8080

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
            assert config.models["test"][0].api_key == "env-key-123"
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
port = 8080

[providers.p1]
type = "anthropic"
api_key = "k"
base_url = "https://api.com"
"""
        path = _write_toml(toml)
        try:
            with pytest.raises(SystemExit):
                load_config(path)
        finally:
            path.unlink()

    def test_empty_providers(self):
        toml = """
[server]
host = "127.0.0.1"
port = 8080

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

    def test_unresolved_env_var(self):
        toml = """
[server]
host = "127.0.0.1"
port = 8080

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

    def test_multiple_virtual_models(self):
        toml = """
[server]
host = "127.0.0.1"
port = 8080

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
port = 8080

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
port = 8080

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
            providers = config.models["haiku-router"]
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
port = 8080

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
