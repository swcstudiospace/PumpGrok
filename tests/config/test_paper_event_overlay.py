<<<<<<< HEAD
"""STR-01 (D-04): the paper-event overlay carries 6/40; live stays 3/20."""
=======
"""STR-01 criterion 4: the paper-event overlay widens paper limits; live and paper do not move.

paper-event copies every value of paper.toml and overrides only the two [risk] limits.
"""
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687

from __future__ import annotations

import os
import tomllib
from pathlib import Path

import pytest

<<<<<<< HEAD
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
=======
from pumpgrok.config.settings import OVERLAY_PROFILES, load_settings, overlay_path

OVERLAYS = Path(__file__).resolve().parents[2] / "src" / "pumpgrok" / "config" / "overlays"


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Strip every PUMPGROK_* var and run from an empty directory."""
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


def _risk(profile: str, monkeypatch: pytest.MonkeyPatch) -> tuple[int, int]:
    monkeypatch.setenv("PUMPGROK_PROFILE", profile)
    risk = load_settings().risk
    return risk.max_open_positions, risk.max_trades_per_day


def test_paper_event_is_a_registered_profile() -> None:
    assert "paper-event" in OVERLAY_PROFILES
    assert overlay_path("paper-event") == OVERLAYS / "paper-event.toml"
    assert overlay_path("paper-event").is_file()


def test_paper_event_sets_six_positions_and_forty_trades(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _risk("paper-event", monkeypatch) == (6, 40)


def test_live_overlay_still_sets_three_and_twenty(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _risk("live", monkeypatch) == (3, 20)


def test_paper_overlay_is_unchanged(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _risk("paper", monkeypatch) == (3, 20)


def test_paper_event_copies_every_paper_value_but_the_two_limits() -> None:
    paper = tomllib.loads((OVERLAYS / "paper.toml").read_text(encoding="utf-8"))
    widened = tomllib.loads((OVERLAYS / "paper-event.toml").read_text(encoding="utf-8"))

    expected = {section: dict(values) for section, values in paper.items()}
    expected["risk"]["max_open_positions"] = 6
    expected["risk"]["max_trades_per_day"] = 40
    assert widened == expected


def test_paper_event_keeps_live_disabled_and_paper_mode() -> None:
    widened = tomllib.loads((OVERLAYS / "paper-event.toml").read_text(encoding="utf-8"))
    assert widened["execution"]["mode"] == "paper"
    assert widened["live"]["enabled"] is False
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
