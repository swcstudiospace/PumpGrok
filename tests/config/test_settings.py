"""Loader slice: defaults, mode precedence, overlays, nested overrides."""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

import pytest

from pumpgrok.config.settings import (
    ConfigError,
    allowed_env_names,
    find_unknown_env,
    load_settings,
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every PUMPGROK_* var so tests see only what they set."""
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


def _write_toml(path: Path, body: str) -> str:
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_fresh_settings_default_paper(clean_env: None) -> None:
    assert load_settings().effective_mode == "paper"


def test_env_mode_beats_toml_execution_mode(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _write_toml(tmp_path / "op.toml", '[execution]\nmode = "live"\n')
    monkeypatch.setenv("PUMPGROK_CONFIG", config)
    monkeypatch.setenv("PUMPGROK_MODE", "paper")
    assert load_settings().effective_mode == "paper"


def test_cli_init_beats_env_and_toml(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _write_toml(tmp_path / "op.toml", '[execution]\nmode = "live"\n')
    monkeypatch.setenv("PUMPGROK_CONFIG", config)
    monkeypatch.setenv("PUMPGROK_MODE", "paper")
    assert load_settings(mode="live").effective_mode == "live"


def test_nested_env_overrides_default(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUMPGROK_RISK__MAX_TRADE_FRACTION", "0.01")
    assert load_settings().risk.max_trade_fraction == Decimal("0.01")


def test_unknown_profile_raises(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUMPGROK_PROFILE", "staging")
    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    assert "staging" in str(excinfo.value)


def test_missing_operator_overlay_raises(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PUMPGROK_CONFIG", str(tmp_path / "absent.toml"))
    with pytest.raises(ConfigError) as excinfo:
        load_settings()
    assert "absent.toml" in str(excinfo.value)


def test_config_file_applies_after_overlay(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Same key in PUMPGROK_CONFIG beats the paper overlay value."""
    config = _write_toml(
        tmp_path / "op.toml",
        '[execution]\nmode = "live"\n[risk]\nmax_trades_per_day = 7\n',
    )
    monkeypatch.setenv("PUMPGROK_CONFIG", config)
    settings = load_settings()
    assert settings.effective_mode == "live"
    assert settings.risk.max_trades_per_day == 7


def test_live_overlay_keeps_live_disabled(clean_env: None) -> None:
    overlay = Path(__file__).resolve().parents[2] / "src" / "pumpgrok" / "config" / "overlays"
    for profile in ("dev", "paper", "live"):
        text = (overlay / f"{profile}.toml").read_text(encoding="utf-8")
        assert "[live]" in text
        assert "enabled = false" in text


def test_env_example_keys_are_declared() -> None:
    """Every key in the operator template must be a setting the loader accepts."""
    template = Path(__file__).resolve().parents[2] / ".env.example"
    keys = [
        line.split("=", 1)[0].strip()
        for line in template.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
    ]
    assert keys
    assert find_unknown_env({key: "x" for key in keys}, allowed_env_names()) == []
