"""STR-01 criterion 4: the paper-event overlay widens paper limits; live and paper do not move.

paper-event copies every value of paper.toml and overrides only the two [risk] limits.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

import pytest

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
