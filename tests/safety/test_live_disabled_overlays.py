"""LIV-02 overlay proof: every profile ships with live disabled.

Every TOML file in src/pumpgrok/config/overlays/ carries a [live]
table with enabled set to False, with no exception for the live
profile, which declares intent through execution mode yet stays
disabled at the gate. The committed default in LiveSettings is False
as well. Offline only, ASCII only.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from pumpgrok.config.settings import LiveSettings

REPO_ROOT = Path(__file__).resolve().parents[2]
OVERLAYS_DIR = REPO_ROOT / "src" / "pumpgrok" / "config" / "overlays"

EXPECTED_PROFILES = frozenset({"dev", "paper", "live"})


def _overlay_paths() -> list[Path]:
    return sorted(path for path in OVERLAYS_DIR.glob("*.toml") if path.is_file())


def _live_enabled(path: Path) -> bool | None:
    """Value of [live] enabled in one overlay, or None when absent."""
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    live = data.get("live")
    if not isinstance(live, dict):
        return None
    return live.get("enabled")


def test_every_overlay_disables_live() -> None:
    """LIV-02: each overlay sets [live] enabled to False without exception."""
    assert OVERLAYS_DIR.is_dir()
    paths = _overlay_paths()
    assert paths, "no overlay TOML files found"
    for path in paths:
        assert _live_enabled(path) is False, path.name


def test_live_profile_declares_intent_but_stays_disabled() -> None:
    """G-04: the live profile selects execution.mode live yet gates live off."""
    live_overlay = OVERLAYS_DIR / "live.toml"
    assert live_overlay.is_file()
    with live_overlay.open("rb") as handle:
        data = tomllib.load(handle)
    assert data.get("execution", {}).get("mode") == "live"
    assert data.get("live", {}).get("enabled") is False


def test_overlay_profile_set_is_unchanged() -> None:
    """The overlay set still covers exactly the dev, paper and live profiles."""
    names = {path.stem for path in _overlay_paths()}
    assert names == EXPECTED_PROFILES


def test_live_settings_default_is_disabled() -> None:
    """The committed LiveSettings default keeps live disabled."""
    assert LiveSettings().enabled is False
