"""UPG-05: the scheduled promotion check searches the declared space and gates only its winner.

Manual-ticket and an empty declared space write nothing. Autonomous-paper runs one search over
the whole declared space and applies the gate verdict to the search winner alone. A malformed,
over-limit or out-of-bounds declared space fails at load. due() holds a second check until the
interval has passed on the injected clock, and a harness failure promotes nothing.

Offline only: temp ledger and temp space files, fixture clock, the bundled smoke fixture for
dataset resolution, the harness and holdout boundary replaced by fakes, no network, no sleeps.
The real config/upgrade_space.toml is never read here.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from pumpgrok.backtest.divergence import check
from pumpgrok.backtest.harness import HarnessResult
from pumpgrok.backtest.metrics import MetricsReport
from pumpgrok.backtest.trials import MAX_ELIGIBLE_TRIALS
from pumpgrok.cli import promotion
from pumpgrok.ledger.active_set import read_active_set
from pumpgrok.ledger.autonomy import autonomy_rows, read_autonomy
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.upgrade.bounds import OutOfBoundsError, load_bounds
from pumpgrok.upgrade.gate import REASON_HOLDOUT_FAILED, evaluate_candidate
from pumpgrok.upgrade.params import ParamSet
from pumpgrok.upgrade.scheduled import (
    PROMOTION_CHECK_INTERVAL_S,
    apply_candidate,
    due,
    mark,
)
from pumpgrok.upgrade.space import (
    MAX_DECLARED_CANDIDATES,
    DeclaredSpaceError,
    load_declared_space,
)

BOUNDS = load_bounds()
IN_BOUNDS = ParamSet(filter={"min_unique_buyers": 5})
SECOND = ParamSet(filter={"min_unique_buyers": 7})
RUN_ID = "RUNID-SCHED-01"
HOLDOUT_ID = "sched-holdout"
TS_UTC = "2026-10-30T00:00:00Z"
T0 = 1_800_000_000.0
DATASET = "smoke"
ONE_TEXT = "[[candidate]]\n[candidate.filter]\nmin_unique_buyers = 5\n"
TWO_TEXT = ONE_TEXT + "\n[[candidate]]\n[candidate.filter]\nmin_unique_buyers = 7\n"


@pytest.fixture(autouse=True)
def _run_in_tmp(tmp_path, monkeypatch) -> None:
    """Promotion manifests and search runs land under var/ relative to the working directory."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def ledger(tmp_path):
    PAPER_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    store = LedgerStore(str(PAPER_LEDGER_PATH))
    yield store
    store.close()


def _report() -> MetricsReport:
    """One same-window summary; backtest and paper match, so divergence passes."""
    return MetricsReport(
        total_return=Decimal("0.01"),
        max_drawdown=Decimal("0.005"),
        sharpe_ratio=Decimal("0.10"),
        win_rate=Decimal("0.5"),
        trade_count=4,
        exposure_lamports=1000,
        turnover_lamports=4000,
    )


def _declared(tmp_path, text: str = TWO_TEXT) -> tuple:
    """Write a space file under tmp_path and load it through the real loader."""
    path = tmp_path / "upgrade_space.toml"
    path.write_text(text, encoding="utf-8")
    return load_declared_space(path)


def _grant_autonomy(store: LedgerStore) -> None:
    """Record a human autonomous-paper level, then confirm the reader sees it."""
    store.append_batch(
        autonomy_rows(
            "autonomous-paper",
            "human:SCHED-TEST",
            previous="",
            ts_utc="2026-01-01T00:00:00Z",
            source="paper",
            correlation_id="upgrade-scheduled-test",
        )
    )
    assert read_autonomy(store) == "autonomous-paper"


def _paper_window_rows(store: LedgerStore) -> None:
    """Paper rows that make the window complete: one inside the holdout, one at its end."""
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


def _search_result(winner: ParamSet, *, holdout_net: int = 100) -> HarnessResult:
    """An eligible search result naming winner as the best candidate."""
    return HarnessResult(
        best_params_hash=winner.content_hash,
        holdout_id=HOLDOUT_ID,
        trial_count=3,
        eligible_for_promotion=True,
        holdout_net_lamports=holdout_net,
        best_net_lamports=50,
    )


def _verdict(store: LedgerStore, *, holdout_net: int = 100):
    return evaluate_candidate(
        IN_BOUNDS,
        bounds=BOUNDS,
        search=_search_result(IN_BOUNDS, holdout_net=holdout_net),
        run_id=RUN_ID,
        store=store,
        backtest=_report(),
        paper=_report(),
    )


def _apply(store: LedgerStore, verdict):
    return apply_candidate(
        store,
        verdict,
        candidate_hash=IN_BOUNDS.content_hash,
        run_id=RUN_ID,
        holdout_id=HOLDOUT_ID,
        divergence=check(_report(), _report()),
        trial_count=3,
        bounds=BOUNDS,
        param_set=IN_BOUNDS,
        by="gate:promotion-check",
        ts_utc=TS_UTC,
        source="replay",
        correlation_id="upgrade-scheduled-test",
    )


def _no_search(*_args, **_kwargs):
    raise AssertionError("the search must not run")


def _fake_search(winner: ParamSet, calls: list[dict]):
    """A stand-in harness search that records its space and names winner as the best set."""

    def _search(dataset, space, n_trials, seed, **_kwargs) -> HarnessResult:
        calls.append(
            {
                "dataset": dataset,
                "space": [dict(entry) for entry in space],
                "n_trials": n_trials,
                "seed": seed,
            }
        )
        return _search_result(winner)

    return _search


def _fake_holdout(**_kwargs) -> SimpleNamespace:
    """A stand-in holdout summary: the window metrics the gate and divergence compare."""
    return SimpleNamespace(
        window_metrics=_report(),
        backtest_result=None,
        elapsed_days=Decimal("1"),
        window_end_ts=T0,
    )


def _fake_paper_gate(**_kwargs) -> SimpleNamespace:
    return SimpleNamespace(paper_metrics=_report())


def _fake_harness(monkeypatch, winner: ParamSet, calls: list[dict]) -> None:
    """Replace only the harness search and the holdout and paper boundary around it."""
    monkeypatch.setattr(promotion, "run_search", _fake_search(winner, calls))
    monkeypatch.setattr(promotion, "_evaluate_holdout", _fake_holdout)
    monkeypatch.setattr(promotion, "_paper_gate", _fake_paper_gate)


def test_manual_ticket_skips_and_writes_nothing(ledger, tmp_path, monkeypatch) -> None:
    """Below autonomous-paper the check returns skipped without searching, adds no rows."""
    monkeypatch.setattr(promotion, "run_search", _no_search)
    before = ledger.count()
    outcome = promotion.run_promotion_check(
        ledger,
        DATASET,
        clock=FixtureClock(T0),
        space=_declared(tmp_path),
        seed=0,
        initial_equity_lamports=0,
    )
    assert outcome == "skipped"
    assert ledger.count() == before
    assert read_active_set(ledger) is None
    assert not (tmp_path / "var" / "upgrade").exists()
    assert not (tmp_path / "var" / "backtest").exists()


@pytest.mark.parametrize("autonomous", [False, True])
def test_empty_declared_space_is_skipped_at_every_level(
    ledger, tmp_path, monkeypatch, autonomous
) -> None:
    """An empty space is skipped at each autonomy level, with no search and no rows."""
    monkeypatch.setattr(promotion, "run_search", _no_search)
    if autonomous:
        _grant_autonomy(ledger)
    before = ledger.count()
    outcome = promotion.run_promotion_check(
        ledger,
        DATASET,
        clock=FixtureClock(T0),
        space=_declared(tmp_path, ""),
        seed=0,
        initial_equity_lamports=0,
    )
    assert outcome == "skipped"
    tick = promotion.make_promotion_check(DATASET, space=(), seed=0, initial_equity_lamports=0)
    tick(ledger, FixtureClock(T0))
    assert ledger.count() == before
    assert read_active_set(ledger) is None
    assert not (tmp_path / "var" / "upgrade").exists()
    assert not (tmp_path / "var" / "backtest").exists()


def test_header_only_space_file_declares_no_candidates(tmp_path) -> None:
    """A file holding only comments loads as the empty declared space."""
    assert _declared(tmp_path, "# owner lists candidates here\n") == ()


def test_out_of_bounds_candidate_fails_closed(tmp_path) -> None:
    """A declared value outside upgrade_bounds.toml raises OutOfBoundsError at load."""
    text = "[[candidate]]\n[candidate.filter]\nmin_unique_buyers = 5000\n"
    with pytest.raises(OutOfBoundsError, match="out of bounds"):
        _declared(tmp_path, text)


def test_more_than_twenty_candidates_is_refused(tmp_path) -> None:
    """Over the limit raises DeclaredSpaceError; exactly the limit still loads in full."""
    over = "".join(
        f"[[candidate]]\n[candidate.filter]\nmin_unique_buyers = {n}\n"
        for n in range(MAX_DECLARED_CANDIDATES + 1)
    )
    with pytest.raises(DeclaredSpaceError, match="at most 20"):
        _declared(tmp_path, over)
    exactly = "".join(
        f"[[candidate]]\n[candidate.filter]\nmin_unique_buyers = {n}\n"
        for n in range(MAX_DECLARED_CANDIDATES)
    )
    assert len(_declared(tmp_path, exactly)) == MAX_DECLARED_CANDIDATES


@pytest.mark.parametrize(
    "text",
    [
        "[[candidate]]\n[candidate.filter]\nmax_curve_progress = 0.5\n",
        "[[candidate]]\n[candidate.filter]\nno_such_knob = 1\n",
        "[[candidate]]\n[candidate.filter]\nmin_total_score = 1\n",
        "[[candidate]]\nseed = 1\n",
        "[other]\nx = 1\n",
        "candidate = [\n",
    ],
)
def test_malformed_declared_space_is_refused(tmp_path, text) -> None:
    """Floats, inert or unknown knobs, unknown keys and bad TOML all raise DeclaredSpaceError."""
    with pytest.raises(DeclaredSpaceError):
        _declared(tmp_path, text)


def test_autonomous_search_gates_only_the_winner(ledger, tmp_path, monkeypatch) -> None:
    """One search covers the whole declared space; the verdict applies to the winner alone."""
    _grant_autonomy(ledger)
    _paper_window_rows(ledger)
    calls: list[dict] = []
    _fake_harness(monkeypatch, SECOND, calls)
    outcome = promotion.run_promotion_check(
        ledger,
        DATASET,
        clock=FixtureClock(T0),
        space=_declared(tmp_path),
        seed=7,
        initial_equity_lamports=0,
    )
    assert outcome == "promoted"
    assert len(calls) == 1
    assert calls[0]["n_trials"] == 2
    assert calls[0]["seed"] == 7
    assert calls[0]["space"] == [
        {"filter": {"min_unique_buyers": 5}},
        {"filter": {"min_unique_buyers": 7}},
    ]
    assert read_active_set(ledger) == SECOND.content_hash
    promotions = tmp_path / "var" / "upgrade" / "promotions"
    assert (promotions / f"{SECOND.content_hash}.json").is_file()
    assert not (promotions / f"{IN_BOUNDS.content_hash}.json").exists()


def test_winner_already_active_is_skipped(ledger, tmp_path, monkeypatch) -> None:
    """A search winner equal to the active set returns skipped and adds no rows."""
    _grant_autonomy(ledger)
    _paper_window_rows(ledger)
    assert _apply(ledger, _verdict(ledger)) == "promoted"
    before = ledger.count()
    calls: list[dict] = []
    _fake_harness(monkeypatch, IN_BOUNDS, calls)
    outcome = promotion.run_promotion_check(
        ledger,
        DATASET,
        clock=FixtureClock(T0),
        space=_declared(tmp_path, ONE_TEXT),
        seed=0,
        initial_equity_lamports=0,
    )
    assert outcome == "skipped"
    assert len(calls) == 1
    assert ledger.count() == before
    assert read_active_set(ledger) == IN_BOUNDS.content_hash


def test_harness_failure_returns_failed_and_promotes_nothing(ledger, tmp_path) -> None:
    """Any exception in the harness path returns failed with no active-set row."""
    _grant_autonomy(ledger)
    _paper_window_rows(ledger)
    before = ledger.count()
    outcome = promotion.run_promotion_check(
        ledger,
        "no-such-dataset",
        clock=FixtureClock(T0),
        space=_declared(tmp_path),
        seed=0,
        initial_equity_lamports=0,
    )
    assert outcome == "failed"
    assert ledger.count() == before
    assert read_active_set(ledger) is None


def test_blocked_winner_escalates_without_active_set(ledger, tmp_path) -> None:
    """A failed holdout on the winner escalates once and writes no active-set row."""
    _grant_autonomy(ledger)
    _paper_window_rows(ledger)
    verdict = _verdict(ledger, holdout_net=0)
    assert verdict.reason == REASON_HOLDOUT_FAILED
    assert _apply(ledger, verdict) == "escalated"
    assert read_active_set(ledger) is None
    assert not (tmp_path / "var" / "upgrade").exists()
    assert not (tmp_path / "var" / "backtest").exists()
    escalations = ledger.read(types=["Escalation"], limit=None)
    assert len(escalations) == 1
    assert escalations[0]["payload"]["kind"] == "upgrade_blocked"


def test_due_blocks_second_check_until_interval_elapses(ledger) -> None:
    """After a mark, due() stays false until PROMOTION_CHECK_INTERVAL_S passes on the clock."""
    clock = FixtureClock(T0)
    assert due(ledger, clock, PROMOTION_CHECK_INTERVAL_S)
    mark(ledger, clock)
    clock.advance_to(T0 + PROMOTION_CHECK_INTERVAL_S - 1.0)
    assert not due(ledger, clock, PROMOTION_CHECK_INTERVAL_S)
    clock.advance_to(T0 + PROMOTION_CHECK_INTERVAL_S)
    assert due(ledger, clock, PROMOTION_CHECK_INTERVAL_S)


def test_closure_runs_check_only_when_due(ledger, tmp_path, monkeypatch) -> None:
    """The closure runs the check on the first tick, then once per interval."""
    calls: list[str] = []

    def _spy(store, dataset_dir, **kwargs) -> str:
        calls.append(str(dataset_dir))
        return "skipped"

    monkeypatch.setattr(promotion, "run_promotion_check", _spy)
    clock = FixtureClock(T0)
    tick = promotion.make_promotion_check(
        DATASET,
        space=_declared(tmp_path),
        seed=0,
        initial_equity_lamports=0,
    )
    tick(ledger, clock)
    tick(ledger, clock)
    assert calls == [DATASET]
    clock.advance_to(T0 + PROMOTION_CHECK_INTERVAL_S)
    tick(ledger, clock)
    assert calls == [DATASET, DATASET]


def test_max_declared_candidates_matches_gate_limit() -> None:
    """The declared-space limit is the gate's eligible-trial limit, kept equal by test."""
    assert MAX_DECLARED_CANDIDATES == MAX_ELIGIBLE_TRIALS
