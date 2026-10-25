"""UPG-01: ParamSet content hashes identify the exact set, never judge it.

Equal sets hash equal, any override change flips the hash, and the hash
never feeds a score, a metric, or a verdict.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

import pumpgrok.upgrade.params as params_module
from pumpgrok.config.settings import ExitsSettings, FilterSettings
from pumpgrok.core.idempotency import canonical_json
from pumpgrok.upgrade.bounds import load_bounds, validate_against_bounds
from pumpgrok.upgrade.params import ParamSet

HASH_RE = re.compile(r"[0-9a-f]{64}")


def test_equal_sets_hash_equal() -> None:
    """Same overrides in any key order give the same identity hash."""
    first = ParamSet(
        filter={"min_unique_buyers": 5, "max_curve_progress": 0.4},
        exits={"stop_loss_pct": 30.0},
    )
    second = ParamSet(
        filter={"max_curve_progress": 0.4, "min_unique_buyers": 5},
        exits={"stop_loss_pct": 30.0},
    )
    assert first.content_hash == second.content_hash
    assert HASH_RE.fullmatch(first.content_hash)


def test_empty_and_none_normalize_to_same_hash() -> None:
    """None and {} both mean no overrides, so they share one hash."""
    assert ParamSet().content_hash == ParamSet(filter=None, exits=None).content_hash
    assert ParamSet().content_hash == ParamSet(filter={}, exits={}).content_hash


def test_any_override_change_flips_hash() -> None:
    """Every override edit changes the identity hash."""
    base = ParamSet(filter={"min_unique_buyers": 5}, exits={"stop_loss_pct": 30.0}).content_hash
    assert (
        ParamSet(filter={"min_unique_buyers": 6}, exits={"stop_loss_pct": 30.0}).content_hash
        != base
    )
    assert (
        ParamSet(filter={"min_unique_buyers": 5}, exits={"stop_loss_pct": 31.0}).content_hash
        != base
    )
    assert (
        ParamSet(
            filter={"min_unique_buyers": 5, "max_risk_score": 6.0},
            exits={"stop_loss_pct": 30.0},
        ).content_hash
        != base
    )
    assert ParamSet(filter=None, exits={"stop_loss_pct": 30.0}).content_hash != base
    assert ParamSet(filter={"min_unique_buyers": 5}, exits=None).content_hash != base


def test_hash_covers_exact_overrides() -> None:
    """The hash is sha256 over the canonical_json of the normalized overrides."""
    params = ParamSet(filter={"min_unique_buyers": 5}, exits=None)
    expected = hashlib.sha256(
        canonical_json({"exits": {}, "filter": {"min_unique_buyers": 5}}).encode("utf-8")
    ).hexdigest()
    assert params.content_hash == expected


def test_unknown_and_inert_knobs_refused() -> None:
    """Unknown keys and inert scoring knobs fail closed at construction."""
    with pytest.raises(ValidationError):
        ParamSet(filter={"no_such_knob": 1})
    with pytest.raises(ValidationError):
        ParamSet(exits={"no_such_knob": 1})
    with pytest.raises(ValidationError):
        ParamSet(filter={"min_total_score": 0.9})


def test_hash_is_identity_only() -> None:
    """The hash names the set; no score, metric, or verdict API reads it."""
    assert not hasattr(ParamSet, "score")
    assert not hasattr(ParamSet, "verdict")
    assert not hasattr(ParamSet, "metric")
    source = Path(params_module.__file__ or "").read_text(encoding="utf-8")
    flat = " ".join(source.split())
    assert "identity only" in flat
    assert "never acts as a score" in flat


def test_bounds_cover_every_tunable_default() -> None:
    """The shipped bounds admit the desk default for every tunable key."""
    params = ParamSet(
        filter={
            key: value
            for key, value in FilterSettings().model_dump().items()
            if key != "min_total_score"
        },
        exits=ExitsSettings().model_dump(),
    )
    validate_against_bounds(params, load_bounds())
