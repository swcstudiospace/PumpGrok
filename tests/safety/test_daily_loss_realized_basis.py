"""Daily-loss halt on both bases compares like with like, in integer lamports.

Under ``daily_loss_basis="realized"`` the halt measures PnL booked today against the day-start
baseline. Cash deployed into an open position and an unrealized swing never trip it. The
``total`` basis keeps cash plus mark-to-market equity as before.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest

from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.risk.limits import EngineLimits

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
EQUITY = 10_000_000_000  # day-start equity, lamports
COST = 6_000_000_000  # entry cost of the one open position
CASH_AFTER_BUY = EQUITY - COST
MINT = "So11111111111111111111111111111111111111112"
UNITS = 1_000_000
HALT_REASON = "daily_loss"


@dataclass
class _Ledger:
    store: LedgerStore
    clock: FixtureClock
    _count: int = 0

    def append(self, event_type: str, payload: dict[str, object]) -> None:
        self._count += 1
        self.store.append(
            ts_utc=format_ts_utc(self.clock.now()),
            source="paper",
            correlation_id="test",
            idempotency_key=f"{event_type}-{self._count}",
            type=event_type,
            payload={"source": "paper", **payload},
        )

    def buy_and_open(self) -> None:
        self._fill("buy", -COST)
        self.append(
            "PositionOpened",
            {
                "mint": MINT,
                "price_entry": "0.000006",
                "token_units": UNITS,
                "cost_basis_lamports": COST,
                "opened_ts_utc": format_ts_utc(self.clock.now()),
            },
        )

    def mark(self, mtm_lamports: int) -> None:
        ts = format_ts_utc(self.clock.now())
        self.append(
            "MarkToMarket",
            {
                "ts_source": ts,
                "cash_lamports": CASH_AFTER_BUY,
                "equity_lamports": CASH_AFTER_BUY + mtm_lamports,
                "unrealized_lamports": mtm_lamports - COST,
                "prices_json": json.dumps(
                    {
                        MINT: {
                            "mtm_lamports": mtm_lamports,
                            "spot": "0.000003",
                            "ts_utc": ts,
                            "source": "curve",
                            "venue_fee_lamports": 0,
                        }
                    }
                ),
            },
        )

    def close(self, proceeds_lamports: int) -> None:
        self._fill("sell", proceeds_lamports)
        self.append(
            "PositionClosed",
            {
                "mint": MINT,
                "price_exit": "0.0000055",
                "proceeds_lamports": proceeds_lamports,
                "realized_pnl_lamports": proceeds_lamports - COST,
                "reason": "stop_loss",
            },
        )

    def _fill(self, side: str, cash_delta: int) -> None:
        self.append(
            "FillRecorded",
            {
                "order_id": f"ord-{self._count + 1}",
                "decision_id": f"dec-{self._count + 1}",
                "side": side,
                "mint": MINT,
                "filled_lamports": abs(cash_delta),
                "filled_units": UNITS,
                "filled_fraction": "1",
                "price_avg": "0.000006",
                "cash_delta_lamports": cash_delta,
            },
        )


@pytest.fixture
def ledger(tmp_path: Path) -> Iterator[_Ledger]:
    clock = FixtureClock(start=START)
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    try:
        yield _Ledger(store=store, clock=clock)
    finally:
        store.close()


def _evaluate(ledger: _Ledger, basis: Literal["total", "realized"]) -> str | None:
    engine = RiskEngine(
        store=ledger.store,
        budget=RiskBudget(),
        ids=IdFactory(ledger.clock, make_rng(11)),
        clock=ledger.clock,
        limits=EngineLimits(daily_loss_basis=basis),
        env={},
    )
    return engine.evaluate_halts()


def test_realized_basis_ignores_cash_deployed_into_a_position(ledger: _Ledger) -> None:
    ledger.buy_and_open()
    ledger.mark(COST)  # held at cost: no unrealized move, no realized PnL
    assert _evaluate(ledger, "realized") is None
    assert ledger.store.read(types=["HaltSet"], limit=None) == []


def test_realized_basis_ignores_an_unrealized_swing_alone(ledger: _Ledger) -> None:
    ledger.buy_and_open()
    ledger.mark(3_000_000_000)  # -30 % unrealized, nothing sold
    assert _evaluate(ledger, "realized") is None
    assert ledger.store.read(types=["HaltSet"], limit=None) == []


@pytest.mark.parametrize(
    ("proceeds", "expected"),
    [
        # Realized -400M is 4 % of day start: below the 5 % floor.
        (5_600_000_000, None),
        # Realized -500M is exactly 5 % of day start: the floor trips (>=).
        (5_500_000_000, HALT_REASON),
    ],
)
def test_realized_basis_trips_on_realized_loss_at_the_floor(
    ledger: _Ledger, proceeds: int, expected: str | None
) -> None:
    ledger.buy_and_open()
    ledger.close(proceeds)
    assert _evaluate(ledger, "realized") == expected
    halts = ledger.store.read(types=["HaltSet"], limit=None)
    assert len(halts) == (0 if expected is None else 1)
    if expected is not None:
        assert halts[0]["payload"]["reason"] == HALT_REASON


@pytest.mark.parametrize(
    ("mtm_lamports", "expected"),
    [
        # Held at cost: total equity 10 SOL, no loss.
        (COST, None),
        # Unrealized -30 % takes total equity to 7 SOL: the total basis counts the mark.
        (3_000_000_000, HALT_REASON),
    ],
)
def test_total_basis_still_counts_the_mark_to_market(
    ledger: _Ledger, mtm_lamports: int, expected: str | None
) -> None:
    ledger.buy_and_open()
    ledger.mark(mtm_lamports)
    assert _evaluate(ledger, "total") == expected
