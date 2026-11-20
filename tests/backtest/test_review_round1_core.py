"""Review round 1 regressions for the backtest core (PR 16).

Covers one normalised candidate hash shared by run_search and ParamSet, so
the promotion gate accepts a real search winner (finding 1); the window score
equals the report's net, closing equity less opening, with every fee counted
once (finding 3); and fold windows never come out empty on equal timestamps
(finding 8). Offline
only: tmp ledgers under tmp_path, bundled smoke fixture, no network, no wall
clock.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from pumpgrok.backtest.equity import equity_lamports
from pumpgrok.backtest.evaluate import (
    CandidateParams,
    EvalWindow,
    _net_lamports,
    evaluate_window,
    fold_windows,
)
from pumpgrok.backtest.harness import run_search
from pumpgrok.backtest.metrics import MetricsReport
from pumpgrok.cli.backtest import _window_curve
from pumpgrok.ledger.autonomy import autonomy_rows
from pumpgrok.ledger.reducer import initial_state, reduce
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.fixtures import event_epoch, load_dataset
from pumpgrok.upgrade.bounds import load_bounds
from pumpgrok.upgrade.gate import (
    REASON_HOLDOUT_FAILED,
    REASON_PASS,
    GateVerdict,
    evaluate_candidate,
)
from pumpgrok.upgrade.params import ParamSet

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "tests" / "fixtures" / "replay" / "smoke"
SEED = 20260101
TS = "2026-01-01T00:00:00Z"
OPENING = 1_000_000


def _report() -> MetricsReport:
    """One same-window summary that passes the divergence check."""
    return MetricsReport(
        total_return=Decimal("0.01"),
        max_drawdown=Decimal("0.005"),
        sharpe_ratio=Decimal("0.10"),
        win_rate=Decimal("0.5"),
        trade_count=4,
        exposure_lamports=1000,
        turnover_lamports=4000,
    )


def _autonomous_store(path: Path) -> LedgerStore:
    """A temp ledger reading as autonomous-paper for the gate."""
    store = LedgerStore(str(path))
    store.append_batch(
        autonomy_rows(
            "autonomous-paper",
            "human:ROUND1-TEST",
            previous="",
            ts_utc=TS,
            source="paper",
            correlation_id="round1-gate",
        )
    )
    return store


def _fill_row(
    order_id: str, side: str, filled: int, fee: int, network: int, cash: int, units: int = 10
) -> dict:
    """One FillRecorded row with explicit money fields."""
    return {
        "ts_utc": TS,
        "source": "replay",
        "correlation_id": "round1-fees",
        "idempotency_key": f"fill|{order_id}",
        "type": "FillRecorded",
        "payload": {
            "source": "replay",
            "order_id": order_id,
            "decision_id": f"DEC-{order_id}",
            "side": side,
            "mint": "MINT",
            "filled_lamports": filled,
            "filled_units": units,
            "filled_fraction": "1",
            "price_avg": "100",
            "venue_fee_lamports": fee,
            "network_cost_lamports": network,
            "cash_delta_lamports": cash,
        },
    }


def _rejection_row(order_id: str, fees: int) -> dict:
    """One OrderRejected row that still paid fees."""
    return {
        "ts_utc": TS,
        "source": "replay",
        "correlation_id": "round1-fees",
        "idempotency_key": f"reject|{order_id}",
        "type": "OrderRejected",
        "payload": {
            "source": "replay",
            "order_id": order_id,
            "decision_id": f"DEC-{order_id}",
            "reason": "slippage",
            "detail": "confirm slippage breach",
            "stage": "CONFIRMING",
            "fees_lamports": fees,
        },
    }


def _open_row(units: int, cost: int) -> dict:
    """One PositionOpened row for the MINT position a buy fill opens."""
    return {
        "ts_utc": TS,
        "source": "replay",
        "correlation_id": "round1-fees",
        "idempotency_key": "open|MINT",
        "type": "PositionOpened",
        "payload": {
            "source": "replay",
            "mint": "MINT",
            "price_entry": "100",
            "token_units": units,
            "cost_basis_lamports": cost,
            "opened_ts_utc": TS,
        },
    }


def _mark_row(mtm: int) -> dict:
    """One MarkToMarket row that marks the open MINT position at mtm lamports."""
    return {
        "ts_utc": TS,
        "source": "replay",
        "correlation_id": "round1-fees",
        "idempotency_key": f"mtm|{mtm}",
        "type": "MarkToMarket",
        "payload": {
            "source": "replay",
            "ts_source": TS,
            "cash_lamports": 0,
            "equity_lamports": 0,
            "unrealized_lamports": 0,
            "prices_json": json.dumps({"MINT": {"mtm_lamports": mtm, "spot": "100"}}),
        },
    }


def _fold_counts(stamps: tuple[float, ...], windows) -> list[int]:
    """Number of stamps each fold window selects."""
    return [sum(1 for ts in stamps if w.start_ts <= ts < w.end_ts) for w in windows.folds]


@pytest.mark.parametrize(
    "mapping",
    [
        {"filter": {"min_unique_buyers": 5}},
        {"filter": {"min_unique_buyers": 5}, "exits": {}},
        {"filter": {"min_unique_buyers": 5}, "exits": None},
    ],
)
def test_candidate_hash_matches_param_set(mapping: dict) -> None:
    """Every spelling of one candidate hashes as the ParamSet gate reads it."""
    assert CandidateParams(**mapping).content_hash == ParamSet(**mapping).content_hash


def test_run_search_winner_hash_is_param_set_hash(tmp_path: Path) -> None:
    """The search winner hash equals the ParamSet hash of the same overrides."""
    result = run_search(
        "smoke",
        [{"filter": {"min_unique_buyers": 5}}],
        1,
        SEED,
        run_id="ROUND1HASH",
        ledger_path=tmp_path / "trials.jsonl",
    )
    assert result.best_params_hash == ParamSet(filter={"min_unique_buyers": 5}).content_hash


def test_gate_accepts_real_search_winner(tmp_path: Path) -> None:
    """A real run_search result reaches the gate checks, not a hash mismatch."""
    params = ParamSet(filter={"min_unique_buyers": 5})
    result = run_search(
        "smoke",
        [{"filter": {"min_unique_buyers": 5}}],
        1,
        SEED,
        run_id="ROUND1GATE",
        ledger_path=tmp_path / "trials.jsonl",
    )
    store = _autonomous_store(tmp_path / "ledger.sqlite")
    try:
        verdict = evaluate_candidate(
            params,
            bounds=load_bounds(),
            search=result,
            run_id="RUNID-ROUND1-01",
            store=store,
            backtest=_report(),
            paper=_report(),
        )
    finally:
        store.close()
    assert isinstance(verdict, GateVerdict)
    expected = REASON_PASS if result.holdout_net_lamports > 0 else REASON_HOLDOUT_FAILED
    assert verdict.reason == expected


def test_net_lamports_counts_each_fee_once(tmp_path: Path) -> None:
    """BUY debits filled plus network cost, SELL proceeds are net, rejections deduct once.

    The 10 venue fee on the buy sits inside its filled amount and the 20 venue
    fee on the sell is already out of its proceeds, so neither is subtracted
    again. Expected net: 2000 - 1005 - 7 = 988.
    """
    path = tmp_path / "fees.sqlite"
    store = LedgerStore(str(path))
    try:
        store.append_batch(
            [
                _fill_row("ORDER-BUY", "buy", filled=1000, fee=10, network=5, cash=-1005),
                _fill_row("ORDER-SELL", "sell", filled=2000, fee=20, network=5, cash=2000),
                _rejection_row("ORDER-REJ", fees=7),
            ]
        )
        store.set_meta("initial_equity_lamports", "1000000")
    finally:
        store.close()
    assert _net_lamports(path) == 2000 - 1005 - 7


def test_replay_score_counts_cash_and_fees_once(tmp_path: Path) -> None:
    """A smoke replay: cash moves once per fill and refusal; the score is the equity change."""
    stamps = [event_epoch(event) for event in load_dataset(SMOKE).events]
    window = EvalWindow(window_id="smoke-full", start_ts=min(stamps), end_ts=float("inf"))
    path = tmp_path / "replay.sqlite"
    score = evaluate_window(
        "smoke",
        CandidateParams(),
        seed=SEED,
        ledger_path=path,
        window=window,
    )
    store = LedgerStore(str(path))
    try:
        rows = store.read(limit=None)
        meta = store.get_meta("initial_equity_lamports")
    finally:
        store.close()
    assert meta is not None
    initial = int(meta)
    fills = [row for row in rows if row["type"] == "FillRecorded"]
    rejections = [row for row in rows if row["type"] == "OrderRejected"]
    assert fills, "the smoke replay must place at least one order"
    cash = sum(int(row["payload"]["cash_delta_lamports"]) for row in fills)
    rejected = sum(int(row["payload"]["fees_lamports"]) for row in rejections)
    state = initial_state(source="replay", initial_equity_lamports=initial, day_utc="")
    for row in rows:
        state = reduce(state, row)
    assert state.cash_lamports == initial + cash - rejected
    assert score == equity_lamports(state) - initial


def _ledger_nets(path: Path, opening: int) -> tuple[int, int]:
    """Selection net of one ledger beside the report's net for the same rows."""
    store = LedgerStore(str(path))
    try:
        rows = store.read(limit=None)
    finally:
        store.close()
    genesis = initial_state(source="backtest", initial_equity_lamports=opening, day_utc="")
    return (_net_lamports(path), _window_curve(genesis, rows)[-1] - opening)


def test_buy_and_hold_is_not_a_loss_in_selection(tmp_path: Path) -> None:
    """An open purchase with no sale or mark is held at cost: selection and report net 0."""
    path = tmp_path / "hold.sqlite"
    store = LedgerStore(str(path))
    try:
        store.set_meta("initial_equity_lamports", str(OPENING))
        store.append_batch(
            [
                _fill_row("ORDER-BUY", "buy", filled=1000, fee=10, network=5, cash=-1005),
                _open_row(units=10, cost=1005),
            ]
        )
    finally:
        store.close()
    selection, report = _ledger_nets(path, OPENING)
    assert selection == report == 0


def test_open_position_selection_equals_report_net(tmp_path: Path) -> None:
    """A partial sale leaves a marked position: selection nets exactly the report's net."""
    path = tmp_path / "open.sqlite"
    store = LedgerStore(str(path))
    try:
        store.set_meta("initial_equity_lamports", str(OPENING))
        store.append_batch(
            [
                _fill_row("ORDER-BUY", "buy", filled=200_000, fee=0, network=0, cash=-200_000),
                _open_row(units=10, cost=200_000),
                _fill_row(
                    "ORDER-SELL", "sell", filled=100_000, fee=0, network=0, cash=100_000, units=4
                ),
                _mark_row(150_000),
            ]
        )
    finally:
        store.close()
    selection, report = _ledger_nets(path, OPENING)
    assert selection == report
    # 100_000 proceeds on 80_000 of sold cost, plus the 150_000 mark on 120_000 remaining cost.
    assert selection == 50_000


def test_equal_timestamps_never_make_an_empty_fold() -> None:
    """Duplicate instants stay together; every fold window holds a stamp."""
    stamps = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 2.0, 3.0, 4.0)
    windows = fold_windows(stamps, "equal-ts", 3)
    counts = _fold_counts(stamps, windows)
    assert all(count > 0 for count in counts), counts
    for left, right in zip(windows.folds, windows.folds[1:], strict=False):
        assert left.end_ts == right.start_ts


def test_too_few_distinct_timestamps_raise() -> None:
    """Fewer distinct pre-holdout instants than folds + 1 refuses, never empties."""
    with pytest.raises(ValueError, match="distinct pre-holdout timestamps"):
        fold_windows((0.0, 0.0, 0.0, 0.0, 1.0, 2.0), "equal-ts", 3)


def test_unique_timestamps_keep_index_geometry() -> None:
    """Strictly increasing stamps keep the block boundaries they had before."""
    stamps = tuple(float(i) for i in range(20))
    windows = fold_windows(stamps, "unique-ts", 2)
    first, second = windows.folds
    assert first.window_id == "unique-ts-test-1"
    assert (first.start_ts, first.end_ts) == (5.0, 10.0)
    assert second.start_ts == 10.0
    assert second.end_ts == pytest.approx(15.2)
    assert windows.holdout.start_ts == pytest.approx(15.2)
