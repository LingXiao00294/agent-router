from __future__ import annotations

import os
import re
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any


class ConfigFileError(Exception):
    """配置文件读写错误."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def mask_key(key: str) -> str:
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


def is_key_masked(api_key: str) -> bool:
    """检查 api_key 是否为空、占位符或已脱敏."""
    if not api_key or api_key == "${PLACEHOLDER}":
        return True
    if re.match(r"^\*+$", api_key):
        return True
    if len(api_key) > 8:
        middle = api_key[4:-4]
        if middle and all(c == "*" for c in middle):
            return True
    return False


def read_config_raw(config_path: str | Path) -> dict:
    path = Path(config_path)
    if not path.exists():
        raise ConfigFileError(f"配置文件不存在: {config_path}")
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigFileError(f"配置文件 TOML 解析失败: {e}") from e


def get_config_masked(config_path: str | Path) -> dict:
    """返回完整配置（api_key 脱敏）."""
    raw = read_config_raw(config_path)
    safe = deepcopy(raw)
    for pdata in safe.get("providers", {}).values():
        if "api_key" in pdata:
            raw_key = pdata["api_key"]
            # has_key 反映运行时是否有可用 key: 展开 ${VAR} 后仍含未解析占位符（变量未设置）→ 视为无可用 key
            expanded = os.path.expandvars(raw_key)
            pdata["has_key"] = "${" not in expanded and bool(expanded)
            pdata["api_key"] = mask_key(raw_key)
    return safe


def list_providers_masked(config_path: str | Path) -> dict[str, dict]:
    raw = read_config_raw(config_path)
    result: dict[str, dict] = {}
    for pname, pdata in raw.get("providers", {}).items():
        result[pname] = {
            "type": pdata.get("type", "anthropic"),
            "base_url": pdata.get("base_url", ""),
            "api_key": mask_key(pdata.get("api_key", "")),
            "timeout_seconds": pdata.get("timeout_seconds", 120.0),
        }
    return result


def list_models_raw(config_path: str | Path) -> dict[str, list[dict]]:
    raw = read_config_raw(config_path)
    models = raw.get("models", {})
    result: dict[str, list[dict]] = {}
    for vname, refs in models.items():
        result[vname] = [
            {
                "provider": r["provider"],
                "model": r["model"],
                "priority": r["priority"],
            }
            for r in sorted(refs, key=lambda r: r.get("priority", 99))
        ]
    return result


def _toml_escape(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def _toml_key(name: str) -> str:
    if re.match(r"^[A-Za-z0-9_-]+$", name):
        return name
    return f'"{_toml_escape(name)}"'


def _toml_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return f'"{_toml_escape(v)}"'
    if isinstance(v, (int, float)):
        return str(v)
    return f'"{_toml_escape(str(v))}"'


def write_toml(config_path: str | Path, data: dict) -> None:
    """将结构化配置原子写入 TOML 文件."""
    lines: list[str] = []

    server = data.get("server", {})
    lines.append("[server]")
    for k, v in server.items():
        if v is None:
            continue
        lines.append(f"{k} = {_toml_value(v)}")
    lines.append("")

    router = data.get("router")
    if router:
        lines.append("[router]")
        for k, v in router.items():
            if v is None:
                continue
            lines.append(f"{k} = {_toml_value(v)}")
        lines.append("")

    providers = data.get("providers", {})
    for name, pdata in providers.items():
        lines.append(f"[providers.{_toml_key(name)}]")
        for k, v in pdata.items():
            if v is None:
                continue
            lines.append(f"{k} = {_toml_value(v)}")
        lines.append("")

    models = data.get("models", {})
    for vname, refs in models.items():
        for ref in refs:
            lines.append(f"[[models.{_toml_key(vname)}]]")
            for k, v in ref.items():
                if v is None:
                    continue
                lines.append(f"{k} = {_toml_value(v)}")
            lines.append("")

    content = "\n".join(lines) + "\n"
    path = Path(config_path)
    tmp_path = path.with_suffix(".tmp")
    try:
        with open(tmp_path, "w") as f:
            f.write(content)
        with open(tmp_path, "rb") as f:
            tomllib.load(f)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    tmp_path.replace(path)
