"""UPG-04: ineligible candidates escalate with a decision request, never promote.

An out-of-bounds candidate and an over-trial-count candidate each produce
one Escalation event plus one JournalNote decision request, both naming the
candidate hash and the single blocking reason, while the active set stays
unchanged and no active-set row is written. Offline only: temp ledger, no
network.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from pumpgrok.backtest.harness import HarnessResult
from pumpgrok.backtest.metrics import MetricsReport
from pumpgrok.ledger.active_set import ACTIVE_SET_KEY, read_active_set, record_active_set
from pumpgrok.ledger.autonomy import autonomy_rows
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.upgrade.bounds import load_bounds
from pumpgrok.upgrade.escalate import ESCALATION_KIND, ESCALATION_SEAT, escalate_candidate
from pumpgrok.upgrade.gate import (
    REASON_OUT_OF_BOUNDS,
    REASON_TOO_MANY_TRIALS,
    evaluate_candidate,
)
from pumpgrok.upgrade.params import ParamSet

IN_BOUNDS = ParamSet(filter={"min_unique_buyers": 5})
OUT_OF_BOUNDS = ParamSet(filter={"min_unique_buyers": 5000})


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


def _search(params: ParamSet, **overrides) -> HarnessResult:
    """An eligible passing search result for params, with caller overrides."""
    fields: dict = {
        "best_params_hash": params.content_hash,
        "holdout_id": "smoke-holdout",
        "trial_count": 3,
        "eligible_for_promotion": True,
        "holdout_net_lamports": 100,
        "best_net_lamports": 50,
    }
    fields.update(overrides)
    return HarnessResult(**fields)


def _autonomous_store(tmp_path) -> LedgerStore:
    """A temp ledger holding an active set and the autonomous-paper level."""
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.append_batch(
        autonomy_rows(
            "autonomous-paper",
            "human:UPGRADE-TEST",
            previous="",
            ts_utc="2026-01-01T00:00:00Z",
            source="paper",
            correlation_id="upgrade-escalation-test",
        )
    )
    record_active_set(
        store,
        IN_BOUNDS,
        "human:UPGRADE-TEST",
        ts_utc="2026-01-01T00:01:00Z",
        source="paper",
        correlation_id="upgrade-escalation-test",
    )
    return store


def test_out_of_bounds_candidate_escalates(tmp_path) -> None:
    """A value outside version-controlled bounds escalates with its reason."""
    store = _autonomous_store(tmp_path)
    try:
        verdict = evaluate_candidate(
            OUT_OF_BOUNDS,
            bounds=load_bounds(),
            search=_search(OUT_OF_BOUNDS),
            run_id="RUNID-TEST-01",
            store=store,
            backtest=_report(),
            paper=_report(),
        )
        assert not verdict.promotion_eligible
        assert verdict.reason == REASON_OUT_OF_BOUNDS

        reason = escalate_candidate(
            store,
            verdict,
            candidate_hash=OUT_OF_BOUNDS.content_hash,
            ts_utc="2026-01-01T00:02:00Z",
            source="paper",
            correlation_id="upgrade-escalation-test",
        )
        assert reason == REASON_OUT_OF_BOUNDS

        escalations = store.read(types=["Escalation"], limit=None)
        assert len(escalations) == 1
        payload = escalations[0]["payload"]
        assert payload["kind"] == ESCALATION_KIND
        assert payload["seat"] == ESCALATION_SEAT
        assert OUT_OF_BOUNDS.content_hash in payload["detail"]
        assert REASON_OUT_OF_BOUNDS in payload["detail"]

        notes = store.read(types=["JournalNote"], limit=None)
        decision = [note for note in notes if "decision requested" in note["payload"]["text"]]
        assert len(decision) == 1
        assert OUT_OF_BOUNDS.content_hash in decision[0]["payload"]["text"]
        assert REASON_OUT_OF_BOUNDS in decision[0]["payload"]["text"]

        assert read_active_set(store) == IN_BOUNDS.content_hash
        changes = [
            row
            for row in store.read(types=["ConfigChanged"], limit=None)
            if ACTIVE_SET_KEY in row["payload"].get("keys_changed", [])
        ]
        assert len(changes) == 1
    finally:
        store.close()


def test_over_trial_count_candidate_escalates(tmp_path) -> None:
    """A 21-trial search escalates with the trial-count reason."""
    store = _autonomous_store(tmp_path)
    try:
        params = ParamSet(filter={"min_unique_buyers": 7})
        verdict = evaluate_candidate(
            params,
            bounds=load_bounds(),
            search=_search(params, trial_count=21, eligible_for_promotion=False),
            run_id="RUNID-TEST-01",
            store=store,
            backtest=_report(),
            paper=_report(),
        )
        assert not verdict.promotion_eligible
        assert verdict.reason == REASON_TOO_MANY_TRIALS

        escalate_candidate(
            store,
            verdict,
            candidate_hash=params.content_hash,
            ts_utc="2026-01-01T00:02:00Z",
            source="paper",
            correlation_id="upgrade-escalation-test",
        )

        escalations = store.read(types=["Escalation"], limit=None)
        assert len(escalations) == 1
        assert params.content_hash in escalations[0]["payload"]["detail"]
        assert REASON_TOO_MANY_TRIALS in escalations[0]["payload"]["detail"]

        notes = store.read(types=["JournalNote"], limit=None)
        decision = [note for note in notes if "decision requested" in note["payload"]["text"]]
        assert len(decision) == 1
        assert REASON_TOO_MANY_TRIALS in decision[0]["payload"]["text"]

        assert read_active_set(store) == IN_BOUNDS.content_hash
    finally:
        store.close()


def test_eligible_verdict_escalates_nothing(tmp_path) -> None:
    """An eligible verdict fails closed: no Escalation, no note, set unchanged."""
    store = _autonomous_store(tmp_path)
    try:
        verdict = evaluate_candidate(
            IN_BOUNDS,
            bounds=load_bounds(),
            search=_search(IN_BOUNDS),
            run_id="RUNID-TEST-01",
            store=store,
            backtest=_report(),
            paper=_report(),
        )
        assert verdict.promotion_eligible
        before = store.count()
        with pytest.raises(ValueError, match="nothing to escalate"):
            escalate_candidate(
                store,
                verdict,
                candidate_hash=IN_BOUNDS.content_hash,
                ts_utc="2026-01-01T00:02:00Z",
                source="paper",
                correlation_id="upgrade-escalation-test",
            )
        assert store.count() == before
        assert read_active_set(store) == IN_BOUNDS.content_hash
    finally:
        store.close()
