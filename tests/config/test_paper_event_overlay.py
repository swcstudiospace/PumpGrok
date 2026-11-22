"""STR-01 (D-04): the paper-event overlay carries 6/40; live stays 3/20."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

import pytest

from pumpgrok.config.settings import load_settings

OVERLAYS = Path(__file__).resolve().parents[2] / "src" / "pumpgrok" / "config" / "overlays"
PAPER_EVENT = OVERLAYS / "paper-event.toml"
LIVE = OVERLAYS / "live.toml"


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


def test_paper_event_toml_values() -> None:
    with open(PAPER_EVENT, "rb") as handle:
        raw = tomllib.load(handle)
    assert raw["execution"]["mode"] == "paper"
    assert raw["risk"]["max_open_positions"] == 6
    assert raw["risk"]["max_trades_per_day"] == 40


def test_live_toml_unchanged() -> None:
    with open(LIVE, "rb") as handle:
        raw = tomllib.load(handle)
    assert raw["risk"]["max_open_positions"] == 3
    assert raw["risk"]["max_trades_per_day"] == 20


def test_paper_event_loads_through_settings(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PUMPGROK_CONFIG", str(PAPER_EVENT))
    settings = load_settings()
    assert settings.risk.max_open_positions == 6
    assert settings.risk.max_trades_per_day == 40


def test_live_profile_unchanged(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUMPGROK_PROFILE", "live")
    settings = load_settings()
    assert settings.risk.max_open_positions == 3
    assert settings.risk.max_trades_per_day == 20
