"""Promotion is a human action only: the serve-path check never changes the level or promotes.

The serve tick runs the scheduled promotion check on its own clock. Even when a human has set
autonomous-paper and the paper window is complete, that automatic tick must not activate a
candidate, write promotion evidence or write any ConfigChanged row. The level a human set is the
level that is read back afterwards, unchanged.

Offline only: temp ledger, temp declared space, fixture clock. The harness search and its holdout
and paper boundary are replaced by fakes, as in tests/upgrade/test_scheduled_promotion.py.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from pumpgrok.backtest.harness import HarnessResult
from pumpgrok.backtest.metrics import MetricsReport
from pumpgrok.cli import promotion
from pumpgrok.ledger.active_set import read_active_set
from pumpgrok.ledger.autonomy import autonomy_rows, read_autonomy
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.upgrade.params import ParamSet
from pumpgrok.upgrade.scheduled import PROMOTION_CHECK_INTERVAL_S
from pumpgrok.upgrade.space import load_declared_space

SECOND = ParamSet(filter={"min_unique_buyers": 7})
HOLDOUT_ID = "human-only-holdout"
T0 = 1_800_000_000.0
DATASET = "smoke"
TWO_TEXT = (
    "[[candidate]]\n[candidate.filter]\nmin_unique_buyers = 5\n"
    "\n[[candidate]]\n[candidate.filter]\nmin_unique_buyers = 7\n"
)


@pytest.fixture(autouse=True)
def _run_in_tmp(tmp_path, monkeypatch) -> None:
    """Promotion manifests and search runs land under var/ relative to the working directory."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def ledger():
    PAPER_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    store = LedgerStore(str(PAPER_LEDGER_PATH))
    yield store
    store.close()


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


def _space(tmp_path):
    path = tmp_path / "upgrade_space.toml"
    path.write_text(TWO_TEXT, encoding="utf-8")
    return load_declared_space(path)


def _serve_ticks(ledger, tmp_path, count: int) -> None:
    """Run the serve closure once per promotion interval, as the serve loop does."""
    tick = promotion.make_promotion_check(
        DATASET,
        space=_space(tmp_path),
        seed=7,
        initial_equity_lamports=0,
    )
    clock = FixtureClock(T0)
    for _ in range(count):
        tick(ledger, clock)
        clock.advance_to(clock.now() + PROMOTION_CHECK_INTERVAL_S)


def _config_rows(store: LedgerStore) -> int:
    return len(store.read(types=["ConfigChanged"], limit=None))


@pytest.mark.parametrize("policy", ["manual-ticket", "autonomous-paper"])
def test_serve_tick_writes_no_config_row_and_keeps_the_human_level(
    ledger, tmp_path, monkeypatch, policy
) -> None:
    """Ticks write no ConfigChanged row, and the level a human set reads back unchanged."""
    _human_level(ledger, policy)
    _paper_window_complete(ledger)
    _fake_harness(monkeypatch, SECOND)
    before = _config_rows(ledger)
    _serve_ticks(ledger, tmp_path, count=3)
    assert read_autonomy(ledger) == policy
    assert _config_rows(ledger) == before


def test_serve_tick_never_activates_a_candidate_in_paper(ledger, tmp_path, monkeypatch) -> None:
    """Even at autonomous-paper with a complete window, the automatic tick activates nothing."""
    _human_level(ledger, "autonomous-paper")
    _paper_window_complete(ledger)
    _fake_harness(monkeypatch, SECOND)
    _serve_ticks(ledger, tmp_path, count=1)
    assert read_active_set(ledger) is None
    assert not (tmp_path / "var" / "upgrade" / "promotions").exists()
