"""RT-04 / criterion 11: an exit deadline set before a crash is re-armed after the rebuild.

The max-hold deadline is the position's opening time plus max_hold_seconds, read from the ledger's
PositionOpened row. A desk that crashes and rebuilds from a fresh store at START+1000 must re-arm
the deadline the position was opened with, not one hold period after the restart. The max-hold
rule then fires at that same time. The clock is a FixtureClock, the curve is a fixed double, and
nothing is skipped.
"""

from __future__ import annotations

from pathlib import Path

from pumpgrok.config.settings import ExitsSettings
from pumpgrok.execution.paper_adapter.models import CurveSnapshot
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.ledger.ticket_refs import append_with_ticket_ref
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.supervisor.exit_rules import ExitRules, LedgerExitBook
from pumpgrok.supervisor.recovery import rebuild_desk_state

MINT = "MintHold11111111111111111111111111111111111"
START = 1_700_000_000.0
DEADLINE = START + 3600.0
CFG = ExitsSettings(
    stop_loss_pct=30.0,
    take_profit_pct=120.0,
    trailing_stop_pct=35.0,
    max_hold_seconds=3600.0,
    stop_loss_poll_seconds=15.0,
)


class _Curves:
    """The mint reads 100 lamports over 1 unit: its entry price, so only the hold cap can fire."""

    async def curve(self, mint: str) -> CurveSnapshot:
        return CurveSnapshot(mint=mint, s_lamports=100, t_units=1, complete=False, source="rpc")

    def last_open_reserves(self, mint: str) -> None:
        return None


class _PlaceSell:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int, str]] = []

    async def __call__(self, mint: str, ticket: str, units: int, rule: str) -> dict[str, object]:
        self.calls.append((mint, ticket, units, rule))
        return {"status": "filled", "reason": ""}


def _create(path: Path) -> LedgerStore:
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", "1000000")
    store.set_meta("source", "paper")
    return store


def _open(store: LedgerStore, clock: FixtureClock, mint: str, ticket: str) -> None:
    payload = {
        "source": "paper",
        "mint": mint,
        "price_entry": "100",
        "token_units": 10,
        "cost_basis_lamports": 1000,
        "opened_ts_utc": format_ts_utc(clock.now()),
        "ticket_id": ticket,
    }
    row = {
        "ts_utc": format_ts_utc(clock.now()),
        "source": "paper",
        "correlation_id": "test",
        "idempotency_key": f"open|{ticket}",
        "type": "PositionOpened",
        "payload": payload,
    }
    append_with_ticket_ref(store, row, ticket_id=ticket, strategy_id="momentum_breakout")


async def test_deadline_set_before_the_crash_is_rearmed_and_fires_at_the_same_time(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ledger.sqlite"
    clock = FixtureClock(START)
    store = _create(path)
    try:
        _open(store, clock, MINT, "hold-1")
        book = LedgerExitBook(CFG)
        book.sync(store)
        set_before_crash = book.exit_deadlines()
    finally:
        store.close()  # the crash: the in-memory book is gone with the process
    assert set_before_crash == {MINT: DEADLINE}

    clock.advance_to(START + 1000.0)  # the desk restarts 1000 s after the position opened
    fresh = LedgerStore(str(path))
    try:
        state = rebuild_desk_state(fresh, [], CFG)
        assert state.exit_deadlines == set_before_crash

        place = _PlaceSell()
        rules = ExitRules(
            store=fresh,
            curves=_Curves(),  # type: ignore[arg-type]
            exits=CFG,
            clock=clock,
            place_sell=place,
        )
        clock.advance_to(DEADLINE - 1.0)
        assert await rules.check(clock.now()) == []
        assert place.calls == []

        clock.advance_to(DEADLINE)
        sold = await rules.check(clock.now())
        assert [row.rule for row in sold] == ["max_hold"]
        assert place.calls == [(MINT, "hold-1", 10, "max_hold")]
    finally:
        fresh.close()
