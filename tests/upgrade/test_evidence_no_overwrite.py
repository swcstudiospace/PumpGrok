"""UPG-03: recorded promotion evidence is never overwritten.

The manifest path is named by the candidate hash, so a second promotion of
the same parameter set under another run must not replace the first record.
Different evidence at that path raises PromotionEvidenceConflict and the
first manifest bytes and its journal note survive. Offline only: temp ledger
and temp promotions dir, no network.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pumpgrok.backtest.divergence import DivergenceVerdict
from pumpgrok.core.errors import PumpgrokError
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.upgrade import evidence as evidence_module
from pumpgrok.upgrade.bounds import load_bounds
from pumpgrok.upgrade.evidence import PromotionEvidenceConflict, record_promotion
from pumpgrok.upgrade.params import ParamSet

PARAMS = ParamSet(filter={"min_unique_buyers": 5})
DIVERGENCE = DivergenceVerdict(
    blocks_promotion=False,
    return_gap_pp=0.25,
    sharpe_gap=0.05,
    reasons=(),
)


def _record(store: LedgerStore, promotions_dir: Path, **overrides) -> Path:
    """Record promotion evidence for PARAMS with defaults unless overridden."""
    kwargs = {
        "candidate_hash": PARAMS.content_hash,
        "run_id": "RUNID-FIRST",
        "holdout_id": "smoke-holdout",
        "divergence": DIVERGENCE,
        "trial_count": 3,
        "bounds": load_bounds(),
        "promotions_dir": promotions_dir,
        "ts_utc": "2026-01-01T00:00:00Z",
        "source": "paper",
        "correlation_id": "upgrade-evidence-test",
    }
    kwargs.update(overrides)
    return record_promotion(store, **kwargs)


def test_second_record_at_same_hash_keeps_first_manifest(tmp_path) -> None:
    """A later promotion under another run is refused; the first record survives."""
    promotions_dir = tmp_path / "promotions"
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:
        path = _record(store, promotions_dir, run_id="RUNID-FIRST")
        first_bytes = path.read_bytes()

        with pytest.raises(PromotionEvidenceConflict) as excinfo:
            _record(
                store,
                promotions_dir,
                run_id="RUNID-SECOND",
                trial_count=7,
                ts_utc="2026-01-02T00:00:00Z",
            )

        assert path.read_bytes() == first_bytes
        assert excinfo.value.fields["run_id"] == "RUNID-SECOND"
        assert excinfo.value.fields["path"] == str(path)
        assert len(store.read(types=["JournalNote"], limit=None)) == 1
    finally:
        store.close()


def test_conflict_error_is_typed_and_stable() -> None:
    """The conflict is a PumpgrokError with a stable machine-readable code."""
    assert issubclass(PromotionEvidenceConflict, PumpgrokError)
    assert PromotionEvidenceConflict.code == "promotion_evidence_conflict"


def test_identical_rerecord_is_allowed(tmp_path) -> None:
    """Re-recording identical evidence rewrites nothing and does not raise."""
    promotions_dir = tmp_path / "promotions"
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:
        path = _record(store, promotions_dir)
        first_bytes = path.read_bytes()
        again = _record(store, promotions_dir, ts_utc="2026-01-02T00:00:00Z")
        assert again == path
        assert path.read_bytes() == first_bytes
    finally:
        store.close()


def test_exclusive_create_race_keeps_first_bytes(tmp_path, monkeypatch) -> None:
    """A conflicting file landing just before the create is never replaced."""
    promotions_dir = tmp_path / "promotions"
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:
        path = evidence_module.promotion_manifest_path(PARAMS.content_hash, promotions_dir)
        racer_bytes = b'{"run_id": "RUNID-RACER"}'
        real_create = evidence_module._create_exclusive

        def racing_create(target: Path, data: bytes) -> None:
            # Another recorder wins the window between the decision and the create.
            target.write_bytes(racer_bytes)
            real_create(target, data)

        monkeypatch.setattr(evidence_module, "_create_exclusive", racing_create)

        with pytest.raises(PromotionEvidenceConflict):
            _record(store, promotions_dir, run_id="RUNID-SECOND", trial_count=7)

        assert path.read_bytes() == racer_bytes
        assert len(store.read(types=["JournalNote"], limit=None)) == 0
    finally:
        store.close()
