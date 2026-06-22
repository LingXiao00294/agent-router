from __future__ import annotations

import tempfile
from pathlib import Path

from typer.testing import CliRunner

from agent_router.cli.app import app

runner = CliRunner()


def _write_toml(content: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False)
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


_SAMPLE_TOML = """
[server]
host = "127.0.0.1"
port = 9456

[providers.p1]
type = "anthropic"
api_key = "sk-test-key"
base_url = "https://api.anthropic.com"

[[models.test-model]]
provider = "p1"
model = "claude-test"
priority = 1
"""


class TestCLI:
    def test_version(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.stdout

    def test_config_validate_ok(self):
        path = _write_toml(_SAMPLE_TOML)
        try:
            result = runner.invoke(app, ["-c", str(path), "-o", "json", "config", "validate"])
            assert result.exit_code == 0
            assert '"ok": true' in result.stdout or '"ok":true' in result.stdout.replace(" ", "")
        finally:
            path.unlink()

    def test_config_validate_fail(self):
        result = runner.invoke(app, ["-c", "/nonexistent/config.toml", "config", "validate"])
        assert result.exit_code == 1

    def test_models_list(self):
        path = _write_toml(_SAMPLE_TOML)
        try:
            result = runner.invoke(app, ["-c", str(path), "-o", "json", "models", "list"])
            assert result.exit_code == 0
            assert "test-model" in result.stdout
        finally:
            path.unlink()
