"""Promotion is a human action only: the serve path never changes the level or promotes.

The serve path replays a recorded dataset and starts its seats. It does not run the scheduled
promotion check. Even when a human has set autonomous-paper and the paper window is complete,
starting the serve must not activate a candidate, write promotion evidence or write an autonomy
or active-set ConfigChanged row. The level a human set is the level that is read back afterwards,
unchanged.

Offline only: temp ledger, fixture clock, the bundled smoke replay. The harness search and its
holdout and paper boundary are faked, as in tests/upgrade/test_scheduled_promotion.py.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from pumpgrok.backtest.harness import HarnessResult
from pumpgrok.backtest.metrics import MetricsReport
from pumpgrok.cli import promotion
from pumpgrok.config.settings import FilterSettings
from pumpgrok.ledger.active_set import ACTIVE_SET_KEY, read_active_set
from pumpgrok.ledger.autonomy import autonomy_rows, read_autonomy
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.supervisor.scheduler import build_serve_replay
from pumpgrok.upgrade.params import ParamSet

SECOND = ParamSet(filter={"min_unique_buyers": 7})
HOLDOUT_ID = "human-only-holdout"
T0 = 1_800_000_000.0
SEED = 20260101
SMOKE = Path(__file__).resolve().parent.parent / "fixtures" / "replay" / "smoke"
AUTONOMY_KEY = "autonomy_level"


@pytest.fixture(autouse=True)
def _run_in_tmp(tmp_path, monkeypatch) -> None:
    """Promotion manifests and search runs land under var/ relative to the working directory."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def serve_ledger(tmp_path) -> Path:
    """The ledger the serve replays into; the serve refuses a ledger it did not write."""
    return tmp_path / "serve-ledger.sqlite"


def _report() -> MetricsReport:
    return MetricsReport(
        total_return=Decimal("0.01"),
        max_drawdown=Decimal("0.005"),
        sharpe_ratio=Decimal("0.10"),
        win_rate=Decimal("0.5"),
        trade_count=4,
        exposure_lamports=1000,
        turnover_lamports=4000,
    )


def _human_level(store: LedgerStore, policy: str) -> None:
    """A level a human recorded through the same rows `state autonomy` writes."""
    store.append_batch(
        autonomy_rows(
            policy,
            "human:OPERATOR",
            previous="",
            ts_utc="2026-01-01T00:00:00Z",
            source="paper",
            correlation_id="human-only-test",
        )
    )
    assert read_autonomy(store) == policy


def _paper_window_complete(store: LedgerStore) -> None:
    """Paper rows that finish the window: one inside the holdout, one at its end."""
    store.append_batch(
        [
            {
                "ts_utc": "2026-01-01T00:00:30Z",
                "source": "paper",
                "correlation_id": "window-inside",
                "idempotency_key": "window-inside",
                "type": "JournalNote",
                "payload": {
                    "source": "paper",
                    "seat": "desk",
                    "note_kind": "note",
                    "text": "inside window",
                    "refs": [],
                },
            },
            {
                "ts_utc": format_ts_utc(T0),
                "source": "paper",
                "correlation_id": "window-end",
                "idempotency_key": "window-end",
                "type": "JournalNote",
                "payload": {
                    "source": "paper",
                    "seat": "desk",
                    "note_kind": "note",
                    "text": "window end",
                    "refs": [],
                },
            },
        ]
    )


def _fake_harness(monkeypatch, winner: ParamSet) -> None:
    """Only the search and the holdout and paper boundary are faked; the winner is eligible."""

    def _search(dataset, space, n_trials, seed, **_kwargs) -> HarnessResult:
        return HarnessResult(
            best_params_hash=winner.content_hash,
            holdout_id=HOLDOUT_ID,
            trial_count=n_trials,
            eligible_for_promotion=True,
            holdout_net_lamports=100,
            best_net_lamports=50,
        )

    monkeypatch.setattr(promotion, "run_search", _search)
    monkeypatch.setattr(
        promotion,
        "_evaluate_holdout",
        lambda **_kwargs: SimpleNamespace(
            window_metrics=_report(),
            backtest_result=None,
            elapsed_days=Decimal("1"),
            window_end_ts=T0,
        ),
    )
    monkeypatch.setattr(
        promotion, "_paper_gate", lambda **_kwargs: SimpleNamespace(paper_metrics=_report())
    )


def _serve_start(ledger_path: Path) -> None:
    """Start the serve path over ledger_path, then close the store it hands back."""
    _supervisor, _metrics, store = build_serve_replay(
        SMOKE,
        FilterSettings(),
        seed=SEED,
        clock=FixtureClock(T0),
        ledger_path=ledger_path,
    )
    store.close()


def _promotion_rows(store: LedgerStore) -> list[str]:
    """Idempotency keys of ConfigChanged rows that move the autonomy level or the active set."""
    keys = {AUTONOMY_KEY, ACTIVE_SET_KEY}
    return sorted(
        str(row.get("idempotency_key"))
        for row in store.read(types=["ConfigChanged"], limit=None)
        if keys & set(row.get("payload", {}).get("keys_changed", []))
    )


@pytest.mark.parametrize("policy", ["manual-ticket", "autonomous-paper"])
def test_serve_path_writes_no_promotion_row_and_keeps_the_human_level(
    serve_ledger, monkeypatch, policy
) -> None:
    """Serving writes no autonomy or active-set ConfigChanged row; the human level reads back."""
    _serve_start(serve_ledger)
    store = LedgerStore(str(serve_ledger))
    try:
        _human_level(store, policy)
        _paper_window_complete(store)
        _fake_harness(monkeypatch, SECOND)
        before = _promotion_rows(store)
    finally:
        store.close()
    _serve_start(serve_ledger)
    store = LedgerStore(str(serve_ledger))
    try:
        assert read_autonomy(store) == policy
        assert _promotion_rows(store) == before
    finally:
        store.close()


def test_serve_path_never_activates_a_candidate_in_paper(
    serve_ledger, tmp_path, monkeypatch
) -> None:
    """Even at autonomous-paper with a complete window, serving activates nothing."""
    _serve_start(serve_ledger)
    store = LedgerStore(str(serve_ledger))
    try:
        _human_level(store, "autonomous-paper")
        _paper_window_complete(store)
        _fake_harness(monkeypatch, SECOND)
    finally:
        store.close()
    _serve_start(serve_ledger)
    store = LedgerStore(str(serve_ledger))
    try:
        assert read_active_set(store) is None
    finally:
        store.close()
    assert not (tmp_path / "var" / "upgrade" / "promotions").exists()
