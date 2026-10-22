"""Health port defaults (INV-C-11)."""

from __future__ import annotations

import os

import pytest

from pumpgrok.config.settings import (
    ConfigError,
    Settings,
    allowed_env_names,
    health_port,
    load_settings,
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every PUMPGROK_* var so tests see only what they set."""
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


def test_default_health_port_is_zero(clean_env: None) -> None:
    assert load_settings().health.port == 0


def test_health_port_env_name_is_allowed() -> None:
    assert "PUMPGROK_HEALTH__PORT" in allowed_env_names()


def test_env_overrides_default_port(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUMPGROK_HEALTH__PORT", "8080")
    assert load_settings().health.port == 8080


def test_once_and_replay_disable_health_port(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PUMPGROK_HEALTH__PORT", "8080")
    settings = load_settings()
    assert health_port(settings) == 8080
    assert health_port(settings, once=True) == 0
    assert health_port(settings, replay="smoke") == 0
    assert health_port(settings, once=True, replay="smoke") == 0


def test_health_port_rejects_negative_or_text(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PUMPGROK_HEALTH__PORT", "not-a-port")
    with pytest.raises(ConfigError):
        load_settings()


def test_health_settings_are_frozen() -> None:
    settings = Settings()
    with pytest.raises(Exception):
        settings.health.port = 8080  # type: ignore[misc]


def test_serve_host_defaults_to_loopback(clean_env: None) -> None:
    assert load_settings().health.host == "127.0.0.1"


def test_serve_host_env_name_is_allowed() -> None:
    assert "PUMPGROK_HEALTH__HOST" in allowed_env_names()


def test_serve_host_env_override(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUMPGROK_HEALTH__HOST", "0.0.0.0")
    assert load_settings().health.host == "0.0.0.0"


def test_serve_replay_binds_loopback_by_default() -> None:
    import inspect

    from pumpgrok.supervisor.scheduler import serve_replay

    assert inspect.signature(serve_replay).parameters["host"].default == "127.0.0.1"


def test_health_port_rejects_out_of_range_values(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    for bad in ("99999", "65536", "-1"):
        monkeypatch.setenv("PUMPGROK_HEALTH__PORT", bad)
        with pytest.raises(ConfigError):
            load_settings()
    monkeypatch.setenv("PUMPGROK_HEALTH__PORT", "65535")
    assert load_settings().health.port == 65535
