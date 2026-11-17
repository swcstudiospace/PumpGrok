"""STR-06 / UPG-01: legacy ParamSet and CandidateParams hashes stay byte-identical.

The golden digests below were captured at base commit 0052468 by running the
unchanged code before any Phase 15 plan 15-01 edit. They must never be derived
from the edited code. A strategy section is a new identity dimension; it must
not move any digest that carries no strategy section.
"""

from __future__ import annotations

from typing import Any

from pumpgrok.backtest.candidate import CandidateParams
from pumpgrok.upgrade.params import ParamSet

GOLDEN_AT_BASE_0052468: dict[str, str] = {
    "EMPTY": "d6c9cd2aa6bebb78a249d6fe42fc519d46ac85bcf4af10f96438b054a2990c93",
    "FILTER_ONLY": "ef3835ba6ca1497a508b2035481cd5fb76d156e38a7d2be766dc2dabc558e235",
    "EXITS_ONLY": "32bb517276aecd5b381c6da5323ce59c88c5345ad61233d284d876af3de38a10",
    "BOTH": "227442d800a844e37d9afa06502a9bc6c12d553d7ba8e11a473321eaf55969dc",
}

LEGACY_CASES: dict[str, dict[str, Any]] = {
    "EMPTY": {},
    "FILTER_ONLY": {"filter": {"min_unique_buyers": 5}},
    "EXITS_ONLY": {"exits": {"stop_loss_pct": 30.0}},
    "BOTH": {
        "filter": {"min_unique_buyers": 5, "max_curve_progress": 0.4},
        "exits": {"stop_loss_pct": 30.0},
    },
}


def test_legacy_paramset_hashes_match_golden_at_base() -> None:
    """Every legacy ParamSet digest equals the value captured at 0052468."""
    for name, kwargs in LEGACY_CASES.items():
        assert ParamSet(**kwargs).content_hash == GOLDEN_AT_BASE_0052468[name], name


def test_legacy_candidate_hashes_match_golden_at_base() -> None:
    """CandidateParams carries the same single digest as ParamSet for legacy sets."""
    for name, kwargs in LEGACY_CASES.items():
        assert CandidateParams(**kwargs).content_hash == GOLDEN_AT_BASE_0052468[name], name


def test_absent_or_empty_strategy_section_hashes_as_legacy() -> None:
    """A ParamSet with no strategy section, or an empty one, hashes exactly as before."""
    for name, kwargs in LEGACY_CASES.items():
        golden = GOLDEN_AT_BASE_0052468[name]
        assert ParamSet(**kwargs, strategy=None).content_hash == golden, name
        assert ParamSet(**kwargs, strategy={}).content_hash == golden, name


def test_strategy_section_is_a_distinct_identity() -> None:
    """A strategy parameter adds identity and never collides with a legacy digest."""
    with_strategy = ParamSet(strategy={"momentum_breakout": {"lookback_seconds": 300}})
    assert with_strategy.content_hash not in GOLDEN_AT_BASE_0052468.values()
    assert with_strategy.content_hash != ParamSet().content_hash
