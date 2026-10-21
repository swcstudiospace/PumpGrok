"""Safety config section: defaults, overlay values, env precedence (TOOL-003)."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pumpgrok.config.settings import SafetySettings, SafetyThresholds, load_settings

OVERLAYS = Path(__file__).resolve().parents[3] / "src" / "pumpgrok" / "config" / "overlays"


def test_threshold_defaults_match_review_values() -> None:
    thresholds = SafetyThresholds()
    assert thresholds.kill_below_score == 40.0
    assert thresholds.conditional_below_score == 70.0
    assert thresholds.top10_concentration_warn_pct == 20.0
    assert thresholds.top10_concentration_fail_pct == 25.0
    assert thresholds.liquidity_multiple_min == 10.0
    assert thresholds.creator_share_veto == 0.25
    assert thresholds.top5_share_veto == 0.80
    assert len(SafetyThresholds.model_fields) == 11


def test_settings_carries_safety_section() -> None:
    assert SafetySettings().thresholds.kill_below_score == 40.0


def test_overlays_pin_safety_thresholds() -> None:
    for profile in ("paper", "dev", "live"):
        with (OVERLAYS / f"{profile}.toml").open("rb") as handle:
            data = tomllib.load(handle)
        thresholds = data["safety"]["thresholds"]
        assert thresholds["kill_below_score"] == 40.0
        assert thresholds["conditional_below_score"] == 70.0
        assert len(thresholds) == 11


def test_env_overrides_overlay_threshold(monkeypatch) -> None:
    monkeypatch.setenv("PUMPGROK_SAFETY__THRESHOLDS__KILL_BELOW_SCORE", "30")
    settings = load_settings()
    assert settings.safety.thresholds.kill_below_score == 30.0
    assert settings.safety.thresholds.conditional_below_score == 70.0
