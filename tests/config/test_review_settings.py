"""Review regressions: Telegram token env acceptance and TOML secret refusal."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pumpgrok.config import settings as settings_module
from pumpgrok.config.settings import ConfigError, load_settings
from pumpgrok.tools.notify.telegram import TELEGRAM_ENV_VAR

TELEGRAM_PLANTED = "123456789:PLANTED-TG-TOKEN-zq8x"  # pragma: allowlist secret: test placeholder
TOML_RPC_PLANTED = "PLANTED-TOML-RPC-KEY-4m9n"  # pragma: allowlist secret: test placeholder
TOML_GROK_PLANTED = "PLANTED-TOML-GROK-KEY-8r1s"  # pragma: allowlist secret: test placeholder
ENV_GROK_VALUE = "PLANTED-ENV-GROK-KEY-2w5e"  # pragma: allowlist secret: test placeholder


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


def test_telegram_env_name_matches_sender_constant() -> None:
    assert TELEGRAM_ENV_VAR == "PUMPGROK_TELEGRAM_TOKEN"  # pragma: allowlist secret: env var name
    assert TELEGRAM_ENV_VAR in settings_module.allowed_env_names()


def test_startup_accepts_telegram_token_env(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(TELEGRAM_ENV_VAR, TELEGRAM_PLANTED)
    assert load_settings().notify.allowlist == []


def test_startup_unaffected_when_telegram_unconfigured(clean_env: None) -> None:
    assert load_settings().notify.allowlist == []


def test_telegram_token_value_not_echoed_in_refusal(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(TELEGRAM_ENV_VAR, TELEGRAM_PLANTED)
    monkeypatch.setenv("PUMPGROK_BOGUS", "1")
    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    message = str(excinfo.value)
    assert "PUMPGROK_BOGUS" in message
    assert TELEGRAM_PLANTED not in message
    assert TELEGRAM_ENV_VAR not in message


def test_secret_setting_paths_cover_api_keys() -> None:
    paths = settings_module._secret_setting_paths()
    assert {"rpc.api_key", "grok.api_key"} <= paths
    assert "rpc.endpoints" not in paths


@pytest.mark.parametrize(
    ("section", "value"),
    [("rpc", TOML_RPC_PLANTED), ("grok", TOML_GROK_PLANTED)],
)
def test_toml_bare_api_key_refused(
    clean_env: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    section: str,
    value: str,
) -> None:
    config = tmp_path / "operator.toml"
    config.write_text(f'[{section}]\napi_key = "{value}"\n', encoding="utf-8")
    monkeypatch.setenv("PUMPGROK_CONFIG", str(config))
    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    message = str(excinfo.value)
    assert f"operator.toml:{section}.api_key" in message
    assert value not in message


def test_toml_empty_api_key_refused(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = tmp_path / "operator.toml"
    config.write_text('[rpc]\napi_key = ""\n', encoding="utf-8")
    monkeypatch.setenv("PUMPGROK_CONFIG", str(config))
    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    assert "operator.toml:rpc.api_key" in str(excinfo.value)


def test_env_api_key_still_accepted(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUMPGROK_GROK__API_KEY", ENV_GROK_VALUE)
    monkeypatch.setenv("PUMPGROK_RPC__API_KEY", ENV_GROK_VALUE)
    settings = load_settings()
    assert settings.grok.api_key.get_secret_value() == ENV_GROK_VALUE
    assert settings.rpc.api_key.get_secret_value() == ENV_GROK_VALUE


def test_toml_non_secret_rpc_endpoints_still_accepted(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = tmp_path / "operator.toml"
    config.write_text('[rpc]\nendpoints = ["https://rpc.example.org"]\n', encoding="utf-8")
    monkeypatch.setenv("PUMPGROK_CONFIG", str(config))
    assert load_settings().rpc.endpoints == ["https://rpc.example.org"]
