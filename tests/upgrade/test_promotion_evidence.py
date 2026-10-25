"""UPG-03: every promotion records complete evidence.

record_promotion writes one JSON manifest under var/upgrade/promotions/
named by the new hash, holding the candidate hash, backtest run id,
holdout id, divergence result, trial count, and bounds snapshot, plus a
ledger JournalNote referencing the file. Offline only: temp ledger and
temp promotions dir, no network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pumpgrok.backtest.divergence import DivergenceVerdict
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.upgrade.bounds import load_bounds
from pumpgrok.upgrade.evidence import (
    bounds_snapshot,
    promotion_manifest_path,
    record_promotion,
)
from pumpgrok.upgrade.params import ParamSet

PARAMS = ParamSet(filter={"min_unique_buyers": 5})
RUN_ID = "RUNID-TEST-01"
HOLDOUT_ID = "smoke-holdout"
TRIAL_COUNT = 3
DIVERGENCE = DivergenceVerdict(
    blocks_promotion=False,
    return_gap_pp=0.25,
    sharpe_gap=0.05,
    reasons=(),
)


def _record(tmp_path: Path, **overrides):
    """Record promotion evidence with passing-shaped inputs unless overridden."""
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:
        path = record_promotion(
            store,
            candidate_hash=overrides.pop("candidate_hash", PARAMS.content_hash),
            run_id=overrides.pop("run_id", RUN_ID),
            holdout_id=overrides.pop("holdout_id", HOLDOUT_ID),
            divergence=overrides.pop("divergence", DIVERGENCE),
            trial_count=overrides.pop("trial_count", TRIAL_COUNT),
            bounds=overrides.pop("bounds", load_bounds()),
            promotions_dir=overrides.pop("promotions_dir", tmp_path / "promotions"),
            ts_utc=overrides.pop("ts_utc", "2026-01-01T00:00:00Z"),
            source="paper",
            correlation_id=overrides.pop("correlation_id", "upgrade-evidence-test"),
        )
        notes = store.read(types=["JournalNote"], limit=None)
        return path, notes
    finally:
        store.close()


def test_manifest_holds_every_gate_input(tmp_path) -> None:
    """Every field is present and matches the gate inputs exactly."""
    path, _notes = _record(tmp_path)
    assert path == tmp_path / "promotions" / f"{PARAMS.content_hash}.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["candidate_hash"] == PARAMS.content_hash
    assert manifest["run_id"] == RUN_ID
    assert manifest["holdout_id"] == HOLDOUT_ID
    assert manifest["trial_count"] == TRIAL_COUNT
    assert manifest["divergence"] == {
        "blocks_promotion": False,
        "reasons": [],
        "return_gap_pp": 0.25,
        "sharpe_gap": 0.05,
    }
    assert manifest["bounds_snapshot"] == bounds_snapshot(load_bounds())
    assert manifest["bounds_snapshot"]["filter"]["min_unique_buyers"] == [0, 1000]


def test_journal_note_references_manifest(tmp_path) -> None:
    """The ledger holds one desk note naming the new hash and its file."""
    path, notes = _record(tmp_path)
    assert len(notes) == 1
    payload = notes[0]["payload"]
    assert payload["seat"] == "desk"
    assert payload["note_kind"] == "note"
    assert PARAMS.content_hash in payload["text"]
    assert path.name in payload["text"]


def test_manifest_bytes_are_deterministic(tmp_path) -> None:
    """Identical inputs always write identical bytes, whatever the timestamp."""
    first, _ = _record(tmp_path, ts_utc="2026-01-01T00:00:00Z")
    first_bytes = first.read_bytes()
    second, _ = _record(tmp_path, ts_utc="2026-01-01T00:05:00Z")
    assert second.read_bytes() == first_bytes


def test_bounds_snapshot_covers_both_sections(tmp_path) -> None:
    """The snapshot freezes every filter and exits range the gate enforced."""
    bounds = load_bounds()
    snapshot = bounds_snapshot(bounds)
    assert set(snapshot) == {"filter", "exits"}
    assert set(snapshot["filter"]) == set(bounds.filter)
    assert set(snapshot["exits"]) == set(bounds.exits)
    assert snapshot["exits"]["stop_loss_pct"] == [0.0, 100.0]


def test_malformed_hash_is_refused(tmp_path) -> None:
    """A non-hash candidate writes no manifest and appends no note."""
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:
        with pytest.raises(ValueError, match="64-hex"):
            record_promotion(
                store,
                candidate_hash="not-a-hash",
                run_id=RUN_ID,
                holdout_id=HOLDOUT_ID,
                divergence=DIVERGENCE,
                trial_count=TRIAL_COUNT,
                bounds=load_bounds(),
                promotions_dir=tmp_path / "promotions",
                ts_utc="2026-01-01T00:00:00Z",
                source="paper",
                correlation_id="upgrade-evidence-test",
            )
        assert not (tmp_path / "promotions").exists()
        assert store.read(types=["JournalNote"], limit=None) == []
    finally:
        store.close()


def test_empty_run_id_is_refused(tmp_path) -> None:
    """An empty backtest run id fails closed instead of recording blindly."""
    with pytest.raises(ValueError, match="run_id"):
        _record(tmp_path, run_id="")


def test_promotion_manifest_path_names_new_hash() -> None:
    """The manifest path is <dir>/<new hash>.json, never a placeholder."""
    path = promotion_manifest_path(PARAMS.content_hash)
    assert path == Path("var/upgrade/promotions") / f"{PARAMS.content_hash}.json"
