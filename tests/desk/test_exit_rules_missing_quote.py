"""Regression: a position with no curve quote is not priced as zero.

``ExitRules._price`` returns None for a missing curve snapshot, so a missing curve is never
read as a zero price (which is a full-loss stop). Offline: the curve source has no snapshot.
"""

from __future__ import annotations

from pathlib import Path

from pumpgrok.config.settings import ExitsSettings
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.supervisor.exit_rules import ExitRules

MINT = "MintNoQuote11111111111111111111111111111111111"
START = 1_700_000_000.0

CFG = ExitsSettings(
    stop_loss_pct=30.0,
    take_profit_pct=120.0,
    trailing_stop_pct=35.0,
    max_hold_seconds=3600.0,
    stop_loss_poll_seconds=15.0,
)


class _NoSnapshot:
    """The curve source has no snapshot for the mint: no quote at all."""

    async def curve(self, mint: str) -> None:
        return None

    def last_open_reserves(self, mint: str) -> None:
        return None


class _PlaceSell:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int, str]] = []

    async def __call__(self, mint: str, ticket: str, units: int, rule: str) -> dict[str, object]:
        self.calls.append((mint, ticket, units, rule))
        return {"status": "filled", "reason": ""}


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "no_quote.sqlite"
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


async def test_missing_snapshot_is_no_quote_not_zero(tmp_path: Path) -> None:
    clock = FixtureClock(START)
    store = _store(tmp_path)
    _open(store, clock, MINT, "tick-no-quote")
    place = _PlaceSell()
    rules = ExitRules(
        store=store,
        curves=_NoSnapshot(),  # type: ignore[arg-type]
        exits=CFG,
        clock=clock,
        place_sell=place,
    )
    assert rules.holding()
    assert await rules._price(MINT) is None
    assert place.calls == []
    store.close()
