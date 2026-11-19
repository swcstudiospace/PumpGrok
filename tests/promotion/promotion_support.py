"""Shared helpers for the promotion tests: gate inputs, one active set, attributed paper rows.

Offline only: every helper writes to a temp ledger the test owns.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pumpgrok.backtest.harness import HarnessResult
from pumpgrok.backtest.metrics import MetricsReport
from pumpgrok.ledger.active_set import record_active_set
from pumpgrok.ledger.autonomy import autonomy_rows, read_autonomy
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.ledger.ticket_refs import append_with_ticket_ref
from pumpgrok.promotion.stages import advance_stage, paper_window
from pumpgrok.promotion.thresholds import load_thresholds
from pumpgrok.upgrade.bounds import load_bounds
from pumpgrok.upgrade.params import ParamSet

CORR = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
OPENED_AT = "2026-01-01T00:00:00Z"
CLOSED_AT = "2026-01-10T00:00:00Z"
NOW = "2026-01-20T00:00:00Z"
LATER_TS = "2026-01-21T00:00:00Z"
STRATEGY = "momentum_breakout"
OTHER_STRATEGY = "new_launch_sniper"
HUMAN = "human:PROMO-TEST"
RUN_ID = "RUN-PROMO-TEST-01"
HOLDOUT_ID = "promo-holdout"
_ULID_PREFIX = "01ARZ3NDEKTSV4RRFFQ69G5"


def param_set(min_unique_buyers: int = 5) -> ParamSet:
    """A parameter set; 5 is in bounds, 5000 is out of bounds."""
    return ParamSet(filter={"min_unique_buyers": min_unique_buyers})


def report(total_return: str = "0.01", sharpe: str = "0.10") -> MetricsReport:
    """One backtest-side summary with fixed figures."""
    return MetricsReport(
        total_return=Decimal(total_return),
        max_drawdown=Decimal("0.005"),
        sharpe_ratio=Decimal(sharpe),
        win_rate=Decimal("0.5"),
        trade_count=4,
        exposure_lamports=1000,
        turnover_lamports=4000,
    )


def search_for(params: ParamSet, **overrides: Any) -> HarnessResult:
    """An eligible passing holdout search result for params."""
    fields: dict[str, Any] = {
        "best_params_hash": params.content_hash,
        "holdout_id": HOLDOUT_ID,
        "trial_count": 3,
        "eligible_for_promotion": True,
        "holdout_net_lamports": 100,
        "best_net_lamports": 50,
    }
    fields.update(overrides)
    return HarnessResult(**fields)


def ulid(n: int) -> str:
    """A valid 26-character ULID for the n-th fill or decision, unique for n below 1000."""
    return f"{_ULID_PREFIX}{n:03d}"


def ensure_autonomous(store: LedgerStore) -> None:
    """Record the autonomous-paper level once, the level the gate requires."""
    if read_autonomy(store) != "autonomous-paper":
        store.append_batch(
            autonomy_rows(
                "autonomous-paper",
                HUMAN,
                previous="",
                ts_utc=OPENED_AT,
                source="paper",
                correlation_id=CORR,
            )
        )


def activate(
    store: LedgerStore, *, min_unique_buyers: int = 5, ts_utc: str = OPENED_AT
) -> ParamSet:
    """Record one active parameter set and the autonomous level; return the set."""
    ensure_autonomous(store)
    params = param_set(min_unique_buyers)
    record_active_set(store, params, HUMAN, ts_utc=ts_utc, source="paper", correlation_id=CORR)
    return params


def advance(
    store: LedgerStore,
    params: ParamSet,
    *,
    by: str = HUMAN,
    now_ts: str = NOW,
    ts_utc: str | None = None,
    backtest: MetricsReport | None = None,
    search: HarnessResult | None = None,
) -> dict[str, Any]:
    """One advance_stage call. The backtest side defaults to the window's own paper report.

    With that default the divergence check compares a report with itself and cannot breach.
    """
    if backtest is None:
        window = paper_window(store, STRATEGY, now_ts=now_ts)
        backtest = window[1] if window is not None else report()
    return advance_stage(
        store,
        STRATEGY,
        params=params,
        bounds=load_bounds(),
        search=search if search is not None else search_for(params),
        run_id=RUN_ID,
        backtest=backtest,
        by=by,
        now_ts=now_ts,
        thresholds=load_thresholds(),
        ts_utc=ts_utc if ts_utc is not None else now_ts,
    )


def open_position(
    store: LedgerStore,
    *,
    ticket: str,
    mint: str,
    cost: int = 1000,
    strategy: str = STRATEGY,
) -> None:
    """Open one paper position attributed to strategy through its ticket."""
    payload = {
        "source": "paper",
        "mint": mint,
        "price_entry": "1",
        "token_units": 1000,
        "cost_basis_lamports": cost,
        "opened_ts_utc": OPENED_AT,
        "ticket_id": ticket,
    }
    row = {
        "ts_utc": OPENED_AT,
        "source": "paper",
        "correlation_id": CORR,
        "idempotency_key": f"open|{ticket}|{mint}",
        "type": "PositionOpened",
        "payload": payload,
    }
    append_with_ticket_ref(store, row, ticket_id=ticket, strategy_id=strategy)


def close_position(
    store: LedgerStore, *, mint: str, pnl: int, index: int, cost: int = 1000
) -> None:
    """Close the paper position on mint with realized pnl lamports."""
    payload = {
        "source": "paper",
        "mint": mint,
        "price_exit": "1",
        "proceeds_lamports": cost + pnl,
        "realized_pnl_lamports": pnl,
        "reason": "take_profit",
    }
    store.append_batch(
        [
            {
                "ts_utc": CLOSED_AT,
                "source": "paper",
                "correlation_id": CORR,
                "idempotency_key": f"close|{mint}|{index}",
                "type": "PositionClosed",
                "payload": payload,
            }
        ]
    )


def fill(store: LedgerStore, *, n: int, side: str, mint: str, lamports: int) -> None:
    """One paper fill on mint. n makes its order and decision ids unique."""
    order_id = ulid(n)
    store.append_batch(
        [
            {
                "ts_utc": OPENED_AT if side == "buy" else CLOSED_AT,
                "source": "paper",
                "correlation_id": CORR,
                "idempotency_key": f"fill|{order_id}",
                "type": "FillRecorded",
                "payload": {
                    "source": "paper",
                    "order_id": order_id,
                    "decision_id": order_id,
                    "side": side,
                    "mint": mint,
                    "filled_lamports": lamports,
                    "filled_units": 1000,
                    "filled_fraction": "1",
                    "price_avg": "1",
                    "venue_tx_ref": f"dry_run:{order_id}",
                    "latency_s": "0",
                },
            }
        ]
    )


def paper_history(
    store: LedgerStore,
    *,
    wins: int,
    losses: int,
    win_lamports: int = 10,
    first_index: int = 1,
) -> None:
    """Trades in order: wins (+win_lamports each), then losses (-5 each).

    Each trade is one ticketed position on its own mint, bought and then sold with a fill row on
    each side, so every fill and close belongs to a position the strategy opened. Call once per
    ledger per block of trades; first_index keeps ids and mints distinct across blocks.
    """
    trades = [win_lamports] * wins + [-5] * losses
    for offset, pnl in enumerate(trades):
        index = first_index + offset
        mint = f"MintPromo{index}"
        open_position(store, ticket=f"SOL-20260101-{index:03d}", mint=mint)
        fill(store, n=2 * index, side="buy", mint=mint, lamports=1000)
        fill(store, n=2 * index + 1, side="sell", mint=mint, lamports=1000 + pnl)
        close_position(store, mint=mint, pnl=pnl, index=index)
