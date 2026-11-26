"""S-X1: one failing exit sell does not abort the checks for later positions.

A rule sell whose place_sell raises is recorded with status ``error`` and the pass goes on to the
next position. The failed position is not held out, so the next pass offers it again. The book is
rebuilt from the ledger in a finally, so it matches the ledger even when the pass raised.

Regression: before the fix, ``ExitRules._sell`` awaited ``self._place_sell`` with no guard
(exit_rules.py:219 on the unfixed file), so the RuntimeError ended ``check`` and the second mint's
sell was never attempted. Offline: the curve is a fixed double and every sell goes to a double.
"""

from __future__ import annotations

from pathlib import Path

from pumpgrok.config.settings import ExitsSettings
from pumpgrok.execution.paper_adapter.models import CurveSnapshot
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.supervisor.exit_rules import ExitRules

FIRST = "MintFirst1111111111111111111111111111111111"
SECOND = "MintSecond111111111111111111111111111111111"
START = 1_700_000_000.0
CFG = ExitsSettings(
    stop_loss_pct=30.0,
    take_profit_pct=120.0,
    trailing_stop_pct=35.0,
    max_hold_seconds=3600.0,
    stop_loss_poll_seconds=15.0,
)


class _Curves:
    """Every mint reads 50 lamports over 1 unit: a 50% fall from the 100 entry (stop loss)."""

    async def curve(self, mint: str) -> CurveSnapshot:
        return CurveSnapshot(mint=mint, s_lamports=50, t_units=1, complete=False, source="rpc")

    def last_open_reserves(self, mint: str) -> None:
        return None


class _CompletedCurves:
    """Every mint's curve has completed: each position is closed as graduated."""

    async def curve(self, mint: str) -> CurveSnapshot:
        return CurveSnapshot(mint=mint, s_lamports=100, t_units=1, complete=True, source="rpc")

    def last_open_reserves(self, mint: str) -> tuple[int, int]:
        return (100, 1)


class _VenueRefusesFirst:
    """Raises for the first mint's sell and fills every other sell."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def __call__(self, mint: str, ticket: str, units: int, rule: str) -> dict[str, object]:
        self.calls.append(mint)
        if mint == FIRST:
            raise RuntimeError("venue refused the sell")
        return {"status": "filled", "reason": ""}


class _GraduateRefusesFirst:
    """Raises for the first mint's graduation close and closes every other mint."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def __call__(self, mint: str, last_s: int, last_t: int) -> dict[str, object] | None:
        self.calls.append(mint)
        if mint == FIRST:
            raise RuntimeError("curve close refused")
        return {"status": "filled"}


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "guard.sqlite"
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
    store.append_batch([row])


async def test_failing_sell_does_not_stop_the_pass_for_later_positions(tmp_path: Path) -> None:
    clock = FixtureClock(START)
    store = _store(tmp_path)
    _open(store, clock, FIRST, "tick-first")
    _open(store, clock, SECOND, "tick-second")
    venue = _VenueRefusesFirst()
    rules = ExitRules(
        store=store,
        curves=_Curves(),  # type: ignore[arg-type]
        exits=CFG,
        clock=clock,
        place_sell=venue,
    )

    sold = await rules.check(clock.now())

    assert venue.calls == [FIRST, SECOND]
    assert [(row.mint, row.status, row.reason) for row in sold] == [
        (FIRST, "error", "RuntimeError"),
        (SECOND, "filled", ""),
    ]
    store.close()


async def test_failed_sell_is_offered_again_on_the_next_pass(tmp_path: Path) -> None:
    clock = FixtureClock(START)
    store = _store(tmp_path)
    _open(store, clock, FIRST, "tick-first")
    _open(store, clock, SECOND, "tick-second")
    venue = _VenueRefusesFirst()
    rules = ExitRules(
        store=store,
        curves=_Curves(),  # type: ignore[arg-type]
        exits=CFG,
        clock=clock,
        place_sell=venue,
    )

    await rules.check(clock.now())
    await rules.check(clock.now())

    assert venue.calls.count(FIRST) == 2
    store.close()


async def test_failing_graduation_close_does_not_stop_later_positions(tmp_path: Path) -> None:
    clock = FixtureClock(START)
    store = _store(tmp_path)
    _open(store, clock, FIRST, "tick-first")
    _open(store, clock, SECOND, "tick-second")
    graduate = _GraduateRefusesFirst()
    rules = ExitRules(
        store=store,
        curves=_CompletedCurves(),  # type: ignore[arg-type]
        exits=CFG,
        clock=clock,
        place_sell=_VenueRefusesFirst(),
        graduate=graduate,
    )

    sold = await rules.check(clock.now())

    assert graduate.calls == [FIRST, SECOND]
    assert [(row.mint, row.rule, row.status) for row in sold] == [
        (FIRST, "graduated", "error"),
        (SECOND, "graduated", "filled"),
    ]
    store.close()
