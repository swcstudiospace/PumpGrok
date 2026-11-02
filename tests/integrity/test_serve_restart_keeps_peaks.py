"""A serve restart keeps the trailing-stop peaks already recorded in its ledger.

``build_serve_replay`` runs on every serve start. It must resume the ledger the
previous start wrote: wiping it would delete the ``MarkToMarket`` peak rows before
``LedgerExitBook.sync`` folds them. Deterministic, no network.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from pumpgrok.config.settings import ExitsSettings, FilterSettings
from pumpgrok.engine.models import PRICE_SCALE
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.fixtures import load_dataset
from pumpgrok.supervisor.exit_rules import LedgerExitBook
from pumpgrok.supervisor.scheduler import build_serve_replay, dataset_events_start

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "tests" / "fixtures" / "replay" / "smoke"
SEED = 20260101
MINT = "PeakMint11111111111111111111111111111111111"
ENTRY = Decimal("100")

CFG = ExitsSettings(
    stop_loss_pct=30.0,
    take_profit_pct=120.0,
    trailing_stop_pct=35.0,
    max_hold_seconds=3600.0,
    stop_loss_poll_seconds=15.0,
)


def _open(store: LedgerStore, clock: FixtureClock) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key="serve-peak|open",
        type="PositionOpened",
        payload={
            "source": "paper",
            "mint": MINT,
            "price_entry": str(ENTRY),
            "token_units": 10,
            "cost_basis_lamports": 1000,
            "opened_ts_utc": format_ts_utc(clock.now()),
            "ticket_id": "tick-peak",
        },
    )


def _mark(store: LedgerStore, clock: FixtureClock, spot: str, key: str) -> None:
    mtm = 10 * int(spot)
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key=f"serve-peak|mtm|{key}",
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


def test_second_serve_build_keeps_the_recorded_peak(tmp_path: Path) -> None:
    """A serve restart over the same ledger restores the peak the first run recorded."""
    ledger = tmp_path / "serve.sqlite"
    start = dataset_events_start(load_dataset(SMOKE))
    clock = FixtureClock(start=start)
    _supervisor, _metrics, store = build_serve_replay(
        SMOKE,
        FilterSettings(),
        seed=SEED,
        clock=clock,
        ledger_path=ledger,
    )
    try:
        _open(store, clock)
        _mark(store, clock, "120", "m1")
        _mark(store, clock, "150", "m2")
        rows_before_restart = store.count()
    finally:
        store.close()

    # Serve restart: build_serve_replay runs again over the same path.
    _supervisor, _metrics, restarted = build_serve_replay(
        SMOKE,
        FilterSettings(),
        seed=SEED,
        clock=FixtureClock(start=start),
        ledger_path=ledger,
    )
    try:
        assert restarted.count() == rows_before_restart
        book = LedgerExitBook(CFG)
        book.sync(restarted)
        assert book.positions[MINT].peak_price == 150 * PRICE_SCALE
    finally:
        restarted.close()
