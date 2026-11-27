"""STR-01: the frozen Strategy protocol holds id, version id and BOUNDS."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pumpgrok.strategies.base import (
    Intent,
    bounds_for,
    code_digest,
    source_digest,
    strategy_version_id,
    version_id,
)
from pumpgrok.upgrade.bounds import load_bounds

BOUNDS_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "pumpgrok" / "config" / "upgrade_bounds.toml"
)


def _toml_strategy_bounds() -> dict[str, dict[str, tuple[int, int]]]:
    with open(BOUNDS_PATH, "rb") as handle:
        raw = tomllib.load(handle)
    parsed: dict[str, dict[str, tuple[int, int]]] = {}
    for sid, params in raw.get("strategy", {}).items():
        parsed[sid] = {p: (int(v["min"]), int(v["max"])) for p, v in params.items()}
    return parsed


def test_declared_bounds_equal_toml_sections_exactly() -> None:
    """D-02: BOUNDS in code equals [strategy.<ID>.<PARAM>] in the TOML."""
    declared = {
        sid: bounds_for(sid) for sid in ("momentum_breakout", "new_launch_sniper", "mean_reversion")
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
    first = strategy_version_id("momentum_breakout", {"breakout_bps": 100}, code="code-a")
    second = strategy_version_id("momentum_breakout", {"breakout_bps": 101}, code="code-a")
    assert first != second
    assert len(first) == 64


def test_version_id_changes_with_code() -> None:
    first = strategy_version_id("momentum_breakout", {"breakout_bps": 100}, code="code-a")
    second = strategy_version_id("momentum_breakout", {"breakout_bps": 100}, code="code-b")
    assert first != second


def test_version_id_is_stable_for_same_inputs() -> None:
    version = strategy_version_id("mean_reversion", {"deviation_bps": 50}, code="c")
    assert version == strategy_version_id("mean_reversion", {"deviation_bps": 50}, code="c")


def test_bounds_for_legacy_declares_none_and_unknown_fails_loudly() -> None:
    assert bounds_for("legacy_screening") == {}
    try:
        bounds_for("no_such_strategy")
    except ValueError as exc:
        assert "no_such_strategy" in str(exc)
    else:
        raise AssertionError("unknown strategy id accepted")


def test_code_digest_unknown_id_and_real_modules() -> None:

    assert code_digest("legacy_screening") == ""
    first = code_digest("momentum_breakout")
    assert len(first) == 64
    assert first == code_digest("momentum_breakout")
    assert first != code_digest("mean_reversion")


def test_intent_rejects_bad_shape() -> None:
    valid = Intent(strategy_id="momentum_breakout", side="buy", mint="MintAAA", size_lamports=1_000)
    assert valid.reason == ""
    for kwargs in (
        {"strategy_id": "momentum_breakout", "side": "hold", "mint": "M", "size_lamports": 1},
        {"strategy_id": "nope", "side": "buy", "mint": "M", "size_lamports": 1},
        {"strategy_id": "momentum_breakout", "side": "buy", "mint": "", "size_lamports": 1},
        {"strategy_id": "momentum_breakout", "side": "buy", "mint": "M", "size_lamports": True},
        {"strategy_id": "momentum_breakout", "side": "buy", "mint": "M", "size_lamports": 1.5},
    ):
        try:
            Intent(**kwargs)  # type: ignore[arg-type]
        except ValueError:
            continue
        raise AssertionError(f"bad intent accepted: {kwargs}")


def test_source_digest_and_version_id_of_a_strategy_class() -> None:
    class DummyStrategy:
        strategy_id = "momentum_breakout"

    digest = source_digest(DummyStrategy)  # type: ignore[arg-type]
    assert len(digest) == 64
    assert digest == source_digest(DummyStrategy)  # type: ignore[arg-type]
    version = version_id(DummyStrategy, {"breakout_bps": 100})  # type: ignore[arg-type]
    assert len(version) == 64
    assert version != version_id(DummyStrategy, {"breakout_bps": 101})  # type: ignore[arg-type]
