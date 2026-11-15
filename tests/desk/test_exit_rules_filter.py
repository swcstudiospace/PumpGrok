"""Criterion 10 (exit book): the global exit book never double-sells a strategy position.

A position opened under a strategy ticket (ticket ref from 15-03) that already carries a
pending sell order (an OrderPlaced side=sell with no FillRecorded or OrderRejected for its
order id) is not offered to a rule sell again. Non-strategy positions and strategy
positions without a pending sell exit exactly as before. Offline; the curve is a fixed
double and every sell goes to a recording place-sell double.
"""

from __future__ import annotations

from pathlib import Path

from pumpgrok.config.settings import ExitsSettings
from pumpgrok.execution.paper_adapter.models import CurveSnapshot
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.ledger.ticket_refs import append_with_ticket_ref
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.supervisor.exit_rules import ExitRules

MINT = "MintFilter11111111111111111111111111111111111"
OTHER = "MintOther111111111111111111111111111111111111"
START = 1_700_000_000.0
STRATEGY = "momentum_breakout"

CFG = ExitsSettings(
    stop_loss_pct=30.0,
    take_profit_pct=120.0,
    trailing_stop_pct=35.0,
    max_hold_seconds=3600.0,
    stop_loss_poll_seconds=15.0,
)


class _Curves:
    """Fixed curve: 50 lamports over 1 unit, a 50% fall from the 100 entry (stop loss)."""

    async def curve(self, mint: str) -> CurveSnapshot:
        return CurveSnapshot(mint=mint, s_lamports=50, t_units=1, complete=False, source="rpc")

    def last_open_reserves(self, mint: str) -> None:
        return None


class _PlaceSell:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int, str]] = []

    async def __call__(self, mint: str, ticket: str, units: int, rule: str) -> dict[str, object]:
        self.calls.append((mint, ticket, units, rule))
        return {"status": "filled", "reason": ""}


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "exit.sqlite"
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", "1000000")
    store.set_meta("source", "paper")
    return store


def _row(clock: FixtureClock, key: str, event_type: str, payload: dict[str, object]) -> dict:
    return {
        "ts_utc": format_ts_utc(clock.now()),
        "source": "paper",
        "correlation_id": "test",
        "idempotency_key": key,
        "type": event_type,
        "payload": payload,
    }


def _open(
    store: LedgerStore, clock: FixtureClock, mint: str, ticket: str, strategy: str | None
) -> None:
    payload = {
        "source": "paper",
        "mint": mint,
        "price_entry": "100",
        "token_units": 10,
        "cost_basis_lamports": 1000,
        "opened_ts_utc": format_ts_utc(clock.now()),
        "ticket_id": ticket,
    }
    row = _row(clock, f"open|{ticket}", "PositionOpened", payload)
    if strategy is None:
        store.append_batch([row])
    else:
        append_with_ticket_ref(store, row, ticket_id=ticket, strategy_id=strategy)


def _sell_placed(
    store: LedgerStore, clock: FixtureClock, mint: str, ticket: str, order_id: str
) -> None:
    payload = {
        "source": "paper",
        "order_id": order_id,
        "decision_id": f"dec-{order_id}",
        "ticket_id": ticket,
        "side": "sell",
        "mint": mint,
        "slippage_bps": 100,
    }
    store.append_batch([_row(clock, f"sell|{order_id}", "OrderPlaced", payload)])


def _settle(store: LedgerStore, clock: FixtureClock, order_id: str) -> None:
    payload = {
        "source": "paper",
        "order_id": order_id,
        "decision_id": f"dec-{order_id}",
        "reason": "slippage",
        "detail": "",
        "stage": "ACCEPTED",
    }
    store.append_batch([_row(clock, f"rej|{order_id}", "OrderRejected", payload)])


def _close(store: LedgerStore, clock: FixtureClock, mint: str) -> None:
    payload = {
        "source": "paper",
        "mint": mint,
        "price_exit": "50",
        "proceeds_lamports": 500,
        "realized_pnl_lamports": -500,
        "reason": "stop_loss",
    }
    store.append_batch([_row(clock, f"close|{mint}", "PositionClosed", payload)])


def _rules(store: LedgerStore, clock: FixtureClock, place: _PlaceSell) -> ExitRules:
    return ExitRules(
        store=store,
        curves=_Curves(),  # type: ignore[arg-type]
        exits=CFG,
        clock=clock,
        place_sell=place,
    )


async def test_pending_strategy_sell_blocks_second_global_sell(tmp_path: Path) -> None:
    clock = FixtureClock(START)
    store = _store(tmp_path)
    _open(store, clock, MINT, "tick-s1", STRATEGY)
    _sell_placed(store, clock, MINT, "tick-s1", "ord-pending")
    place = _PlaceSell()

    sold = await _rules(store, clock, place).check(clock.now())

    assert place.calls == []
    assert sold == []
    store.close()


async def test_strategy_position_without_pending_sell_still_exits(tmp_path: Path) -> None:
    clock = FixtureClock(START)
    store = _store(tmp_path)
    _open(store, clock, MINT, "tick-s2", STRATEGY)
    place = _PlaceSell()

    sold = await _rules(store, clock, place).check(clock.now())

    assert place.calls == [(MINT, "tick-s2", 10, "stop_loss")]
    assert [row.status for row in sold] == ["filled"]
    store.close()


async def test_settled_strategy_sell_no_longer_blocks(tmp_path: Path) -> None:
    clock = FixtureClock(START)
    store = _store(tmp_path)
    _open(store, clock, MINT, "tick-s3", STRATEGY)
    _sell_placed(store, clock, MINT, "tick-s3", "ord-settled")
    _settle(store, clock, "ord-settled")
    place = _PlaceSell()

    await _rules(store, clock, place).check(clock.now())

    assert place.calls == [(MINT, "tick-s3", 10, "stop_loss")]
    store.close()


async def test_non_strategy_position_with_pending_sell_exits_as_before(tmp_path: Path) -> None:
    clock = FixtureClock(START)
    store = _store(tmp_path)
    _open(store, clock, OTHER, "tick-manual", None)
    _sell_placed(store, clock, OTHER, "tick-manual", "ord-manual")
    place = _PlaceSell()

    await _rules(store, clock, place).check(clock.now())

    assert place.calls == [(OTHER, "tick-manual", 10, "stop_loss")]
    store.close()


async def test_each_position_on_a_mint_is_filtered_by_its_own_ticket(tmp_path: Path) -> None:
    clock = FixtureClock(START)
    store = _store(tmp_path)
    # The fold tracks one open position per mint: the first strategy position closes,
    # then a second strategy re-enters the same mint under its own ticket.
    _open(store, clock, MINT, "tick-first", STRATEGY)
    _sell_placed(store, clock, MINT, "tick-first", "ord-first")
    _close(store, clock, MINT)
    clock.advance_to(START + 60.0)
    _open(store, clock, MINT, "tick-second", "mean_reversion")
    place = _PlaceSell()

    await _rules(store, clock, place).check(clock.now())

    assert place.calls == [(MINT, "tick-second", 10, "stop_loss")]
    store.close()
