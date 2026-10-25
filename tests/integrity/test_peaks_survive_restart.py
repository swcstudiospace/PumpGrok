"""INT-09: trailing-stop peaks survive a serve restart.

The serve loop persists the running peak through the existing ``MarkToMarket``
event type (each row's ``spot``; the reducer ratchets ``price_peak`` from it,
no new R32 type). ``LedgerExitBook.sync`` — the rebuild that runs before every
exit pass, including the first after a restart — restores the persisted peak
into the fresh in-memory track. Deterministic, no network.
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from pathlib import Path

from pumpgrok.config.settings import ExitsSettings
from pumpgrok.engine.exits import apply_price, restore_peak
from pumpgrok.engine.models import PRICE_SCALE, ExitPosition
from pumpgrok.engine.watcher import PositionWatcher
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.supervisor.exit_rules import LedgerExitBook

MINT = "PeakMint11111111111111111111111111111111111"
START = 1_700_000_000.0
ENTRY = Decimal("100")

CFG = ExitsSettings(
    stop_loss_pct=30.0,
    take_profit_pct=120.0,
    trailing_stop_pct=35.0,
    max_hold_seconds=3600.0,
    stop_loss_poll_seconds=15.0,
)


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "peaks.sqlite"
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", "1000000")
    store.set_meta("source", "paper")
    return store


def _open(store: LedgerStore, clock: FixtureClock) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key="open|1",
        type="PositionOpened",
        payload={
            "source": "paper",
            "mint": MINT,
            "price_entry": str(ENTRY),
            "token_units": 10,
            "cost_basis_lamports": 1000,
            "opened_ts_utc": format_ts_utc(clock.now()),
            "ticket_id": "tick-1",
        },
    )

def _mark(store: LedgerStore, clock: FixtureClock, spot: str, key: str) -> None:
    mtm = 10 * int(spot)
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key=f"mtm|{key}",
        type="MarkToMarket",
        payload={
            "source": "paper",
            "ts_source": format_ts_utc(clock.now()),
            "cash_lamports": 0,
            "equity_lamports": mtm,
            "unrealized_lamports": mtm - 1000,
            "prices_json": json.dumps(
                {
                    MINT: {
                        "mtm_lamports": mtm,
                        "venue_fee_lamports": 0,
                        "spot": spot,
                        "source": "curve",
                        "ts_utc": format_ts_utc(clock.now()),
                    }
                }
            ),
        },
    )


def test_peaks_persist_through_marks_and_restore_on_restart(tmp_path: Path) -> None:
    """Marks ratchet the ledger peak; a fresh book restores it, never below entry."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        _open(store, clock)
        _mark(store, clock, "120", "m1")
        _mark(store, clock, "150", "m2")

        book = LedgerExitBook(CFG)
        book.sync(store)
        assert book.positions[MINT].entry_price == 100 * PRICE_SCALE
        assert book.positions[MINT].peak_price == 150 * PRICE_SCALE

        # Serve restart: all in-memory tracks are gone; the fold still holds the peak.
        restarted = LedgerExitBook(CFG)
        restarted.sync(store)
        assert restarted.positions[MINT].peak_price == 150 * PRICE_SCALE
    finally:
        store.close()

    assert restore_peak(100 * PRICE_SCALE, Decimal("150")) == 150 * PRICE_SCALE
    assert restore_peak(100 * PRICE_SCALE, Decimal("50")) == 100 * PRICE_SCALE


def test_restored_peak_feeds_the_first_exit_check(tmp_path: Path) -> None:
    """After a restart, a 40% slide from the restored peak fires trailing_stop."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        _open(store, clock)
        _mark(store, clock, "150", "m1")

        restarted = LedgerExitBook(CFG)
        restarted.sync(store)

        sold: list[tuple[str, int, str]] = []

        async def price_fn(_mint: str) -> int:
            return 90 * PRICE_SCALE

        async def sell_fn(pos: ExitPosition, price: int, reason: str) -> None:
            sold.append((pos.mint, price, reason))

        watcher = PositionWatcher(restarted, price_fn, sell_fn, clock)
        asyncio.run(watcher.check_once(START + 60.0))
        assert [(m, r) for m, _, r in sold] == [(MINT, "trailing_stop")]
    finally:
        store.close()


def test_unmarked_position_restarts_at_entry_and_holds(tmp_path: Path) -> None:
    """Control: with no mark above entry, a 10% dip fires nothing after restart."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        _open(store, clock)

        restarted = LedgerExitBook(CFG)
        restarted.sync(store)
        assert restarted.positions[MINT].peak_price == 100 * PRICE_SCALE

        seen: list[str] = []

        async def price_fn(_mint: str) -> int:
            return 90 * PRICE_SCALE

        async def sell_fn(pos: ExitPosition, price: int, reason: str) -> None:
            seen.append(reason)

        watcher = PositionWatcher(restarted, price_fn, sell_fn, clock)
        asyncio.run(watcher.check_once(START + 60.0))
        assert seen == []
    finally:
        store.close()


def test_in_memory_progress_survives_a_stale_mark(tmp_path: Path) -> None:
    """A re-sync keeps the higher in-memory peak when the latest mark lags it."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        _open(store, clock)
        _mark(store, clock, "150", "m1")

        book = LedgerExitBook(CFG)
        book.sync(store)
        signal = apply_price(
            book.positions[MINT], 160 * PRICE_SCALE, CFG, START + 10.0
        )
        assert signal is None
        assert book.positions[MINT].peak_price == 160 * PRICE_SCALE

        _mark(store, clock, "155", "m2")
        book.sync(store)
        assert book.positions[MINT].peak_price == 160 * PRICE_SCALE
    finally:
        store.close()
