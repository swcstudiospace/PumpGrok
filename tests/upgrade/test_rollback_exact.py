"""UPG-03: rollback restores the exact prior content hash as a real round-trip.

Set A is recorded, set B is promoted through the gate with evidence, then
A is restored in one operation: the live value reads back the content hash
of A and the ledger holds the A, B and restore rows in order. Offline
only: temp ledger and temp promotions dir, no network.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from pumpgrok.backtest.divergence import check
from pumpgrok.backtest.harness import HarnessResult
from pumpgrok.backtest.metrics import MetricsReport
from pumpgrok.ledger.active_set import ACTIVE_SET_KEY, read_active_set, record_active_set
from pumpgrok.ledger.autonomy import autonomy_rows, read_autonomy
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.upgrade.bounds import load_bounds
from pumpgrok.upgrade.evidence import record_promotion
from pumpgrok.upgrade.gate import evaluate_candidate
from pumpgrok.upgrade.params import ParamSet
from pumpgrok.upgrade.rollback import restore_active_set

SET_A = ParamSet(filter={"min_unique_buyers": 5})
SET_B = ParamSet(filter={"min_unique_buyers": 6})
RUN_ID = "RUNID-TEST-01"


def _report() -> MetricsReport:
    """One same-window summary; identical inputs on both sides show no gap."""
    return MetricsReport(
        total_return=Decimal("0.01"),
        max_drawdown=Decimal("0.005"),
        sharpe_ratio=Decimal("0.10"),
        win_rate=Decimal("0.5"),
        trade_count=4,
        exposure_lamports=1000,
        turnover_lamports=4000,
    )


def _passing_search(params: ParamSet) -> HarnessResult:
    """An eligible passing search result for params."""
    return HarnessResult(
        best_params_hash=params.content_hash,
        holdout_id="smoke-holdout",
        trial_count=3,
        eligible_for_promotion=True,
        holdout_net_lamports=100,
        best_net_lamports=50,
    )


def _active_changes(store: LedgerStore) -> list:
    """Active-set ConfigChanged rows in ledger order."""
    return [
        row
        for row in store.read(types=["ConfigChanged"], limit=None)
        if ACTIVE_SET_KEY in row["payload"].get("keys_changed", [])
    ]


def test_promote_then_rollback_round_trip(tmp_path) -> None:
    """Record A, promote B through the gate, restore A: live reads back A."""
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:
        store.append_batch(
            autonomy_rows(
                "autonomous-paper",
                "human:UPGRADE-TEST",
                previous="",
                ts_utc="2026-01-01T00:00:00Z",
                source="paper",
                correlation_id="upgrade-rollback-test",
            )
        )
        bounds = load_bounds()

        record_active_set(
            store,
            SET_A,
            "human:UPGRADE-TEST",
            ts_utc="2026-01-01T00:01:00Z",
            source="paper",
            correlation_id="upgrade-rollback-test",
        )
        assert read_active_set(store) == SET_A.content_hash

        backtest = _report()
        paper = _report()
        verdict = evaluate_candidate(
            SET_B,
            bounds=bounds,
            search=_passing_search(SET_B),
            run_id=RUN_ID,
            store=store,
            backtest=backtest,
            paper=paper,
        )
        assert verdict.promotion_eligible
        record_promotion(
            store,
            candidate_hash=SET_B.content_hash,
            run_id=RUN_ID,
            holdout_id="smoke-holdout",
            divergence=check(backtest, paper),
            trial_count=3,
            bounds=bounds,
            promotions_dir=tmp_path / "promotions",
            ts_utc="2026-01-01T00:02:00Z",
            source="paper",
            correlation_id="upgrade-rollback-test",
        )
        record_active_set(
            store,
            SET_B,
            "gate:UPGRADE-GATE",
            ts_utc="2026-01-01T00:03:00Z",
            source="paper",
            correlation_id="upgrade-rollback-test",
        )
        assert read_active_set(store) == SET_B.content_hash

        restored = restore_active_set(
            store,
            SET_A.content_hash,
            "human:UPGRADE-TEST",
            ts_utc="2026-01-01T00:04:00Z",
            source="paper",
            correlation_id="upgrade-rollback-test",
        )
        assert restored == SET_A.content_hash
        assert read_active_set(store) == SET_A.content_hash

        changes = _active_changes(store)
        assert [row["payload"]["new_hash"] for row in changes] == [
            SET_A.content_hash,
            SET_B.content_hash,
            SET_A.content_hash,
        ]
        assert [row["payload"]["old_hash"] for row in changes] == [
            "",
            SET_A.content_hash,
            SET_B.content_hash,
        ]

        notes = store.read(types=["JournalNote"], limit=None)
        assert any(
            SET_A.content_hash in note["payload"]["text"] and "rollback" in note["payload"]["text"]
            for note in notes
        )
        assert read_autonomy(store) == "autonomous-paper"
    finally:
        store.close()


def test_malformed_prior_hash_writes_nothing(tmp_path) -> None:
    """A non-hash prior restores nothing and appends no rows."""
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:
        record_active_set(
            store,
            SET_A,
            "human:UPGRADE-TEST",
            ts_utc="2026-01-01T00:00:00Z",
            source="paper",
            correlation_id="upgrade-rollback-test",
        )
        before = store.count()
        with pytest.raises(ValueError, match="prior_hash"):
            restore_active_set(
                store,
                "not-a-hash",
                "human:UPGRADE-TEST",
                ts_utc="2026-01-01T00:01:00Z",
                source="paper",
                correlation_id="upgrade-rollback-test",
            )
        assert store.count() == before
        assert read_active_set(store) == SET_A.content_hash
    finally:
        store.close()
