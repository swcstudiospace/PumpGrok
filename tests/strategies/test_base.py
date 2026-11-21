"""STR-01: the frozen Strategy protocol holds id, version id and BOUNDS."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pumpgrok.strategies.base import bounds_for, strategy_version_id
from pumpgrok.upgrade.bounds import load_bounds

BOUNDS_PATH = Path(__file__).resolve().parents[2] / "src" / "pumpgrok" / "config" / "upgrade_bounds.toml"


def _toml_strategy_bounds() -> dict[str, dict[str, tuple[int, int]]]:
    raw = tomllib.load(open(BOUNDS_PATH, "rb"))
    parsed: dict[str, dict[str, tuple[int, int]]] = {}
    for sid, params in raw.get("strategy", {}).items():
        parsed[sid] = {p: (int(v["min"]), int(v["max"])) for p, v in params.items()}
    return parsed


def test_declared_bounds_equal_toml_sections_exactly() -> None:
    """D-02: BOUNDS in code equals [strategy.<ID>.<PARAM>] in the TOML."""
    declared = {
        sid: bounds_for(sid)
        for sid in ("momentum_breakout", "new_launch_sniper", "mean_reversion")
    }
    assert declared == _toml_strategy_bounds()
    assert declared["momentum_breakout"] == {"breakout_bps": (0, 10000)}
    assert bounds_for("legacy_screening") == {}
def test_load_bounds_strategy_sections_match_declared() -> None:
    bounds = load_bounds()
    for sid in ("momentum_breakout", "new_launch_sniper", "mean_reversion"):
        declared = bounds_for(sid)
        assert set(bounds.strategy[sid]) == set(declared)
        for param, (lo, hi) in declared.items():
            kb = bounds.strategy[sid][param]
            assert (kb.minimum, kb.maximum) == (lo, hi)


def test_version_id_changes_with_params() -> None:
    first = strategy_version_id(
        "momentum_breakout", {"breakout_bps": 100}, code="code-a"
    )
    second = strategy_version_id(
        "momentum_breakout", {"breakout_bps": 101}, code="code-a"
    )
    assert first != second
    assert len(first) == 64


def test_version_id_changes_with_code() -> None:
    first = strategy_version_id(
        "momentum_breakout", {"breakout_bps": 100}, code="code-a"
    )
    second = strategy_version_id(
        "momentum_breakout", {"breakout_bps": 100}, code="code-b"
    )
    assert first != second


def test_version_id_is_stable_for_same_inputs() -> None:
    version = strategy_version_id("mean_reversion", {"deviation_bps": 50}, code="c")
    assert version == strategy_version_id("mean_reversion", {"deviation_bps": 50}, code="c")
