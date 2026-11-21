"""STR-06: legacy filter/exits-only ParamSet hashes are byte-identical.

The pins below are the content_hash digests recorded BEFORE strategy
overrides existed. Any change to normalization, payload shape, or hash input
for a set that carries no strategy overrides moves one of these digests and
fails here, so a legacy upgrade trial can never silently change identity
because strategies were added.
"""

from __future__ import annotations

from pumpgrok.upgrade.params import ParamSet

# content_hash of each legacy ParamSet, recorded before STRATEGY support.
PINNED_LEGACY_HASHES: dict[str, str] = {
    "empty": "d6c9cd2aa6bebb78a249d6fe42fc519d46ac85bcf4af10f96438b054a2990c93",
    "filter_only": "ef3835ba6ca1497a508b2035481cd5fb76d156e38a7d2be766dc2dabc558e235",
    "exits_stop": "32bb517276aecd5b381c6da5323ce59c88c5345ad61233d284d876af3de38a10",
    "filter_exits": "227442d800a844e37d9afa06502a9bc6c12d553d7ba8e11a473321eaf55969dc",
}


def _legacy_sets() -> dict[str, ParamSet]:
    return {
        "empty": ParamSet(),
        "filter_only": ParamSet(filter={"min_unique_buyers": 5}),
        "exits_stop": ParamSet(exits={"stop_loss_pct": 30.0}),
        "filter_exits": ParamSet(
            filter={"min_unique_buyers": 5, "max_curve_progress": 0.4},
            exits={"stop_loss_pct": 30.0},
        ),
    }


def test_legacy_hashes_are_byte_identical_to_pre_strategy_digests() -> None:
    sets = _legacy_sets()
    assert set(sets) == set(PINNED_LEGACY_HASHES)
    for name, params in sets.items():
        assert params.content_hash == PINNED_LEGACY_HASHES[name], name


def test_empty_strategy_matches_absent_strategy_hash() -> None:
    """strategy=None and strategy={} both mean no overrides, one hash."""
    assert ParamSet().content_hash == ParamSet(strategy={}).content_hash
    assert ParamSet(filter={"min_unique_buyers": 5}).content_hash == ParamSet(
        filter={"min_unique_buyers": 5}, strategy={},
    ).content_hash
