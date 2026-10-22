"""Review finding 17: ``portfolio.pnl`` must honour ``window`` and ``as_of``.

The fold used to total the whole ledger, so a "today" request included older
trades and a historical ``as_of`` included later ones. Windows are the UTC
calendar day or ISO week (Monday start) that contains ``as_of``, matching the
daily and weekly reports; ``all`` has no lower bound. Both ends are inclusive
of events at exactly ``as_of`` and earlier, and nothing after ``as_of`` counts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools.portfolio.pnl import PnlIn, run_pnl

CORR = "01J0000000000000000000000"
MINT = "PnlWin11111111111111111111111111111111111"
NOON_OCT22 = datetime(2026, 10, 22, 12, tzinfo=UTC)
NOON_OCT21 = datetime(2026, 10, 21, 12, tzinfo=UTC)


def _fill(ts: str, venue_fee: int, network: int) -> tuple[str, str, dict[str, Any]]:
    return (
        "FillRecorded",
        ts,
        {
            "source": "paper",
            "order_id": f"o-{ts}",
            "decision_id": f"d-{ts}",
            "side": "buy",
            "mint": MINT,
            "filled_lamports": 5000,
            "filled_units": 10,
            "filled_fraction": "1",
            "price_avg": "1",
            "venue_fee_lamports": venue_fee,
            "network_cost_lamports": network,
        },
    )


def _close(ts: str, realised: int) -> tuple[str, str, dict[str, Any]]:
    return (
        "PositionClosed",
        ts,
        {
            "source": "paper",
            "mint": MINT,
            "price_exit": "2",
            "proceeds_lamports": 6000,
            "realized_pnl_lamports": realised,
            "reason": "take_profit",
        },
    )


# Oct 1 is far outside any week; Oct 19 is the Monday of the week holding Oct 22.
# The 23:59:59 and 00:00:00 pair straddles the Oct 21/22 day boundary.
SEEDED = (
    _fill("2026-10-01T10:00:00.000000Z", 1000, 0),
    _close("2026-10-01T11:00:00.000000Z", 9000),
    _fill("2026-10-19T08:00:00.000000Z", 100, 0),
    _close("2026-10-21T10:00:00.000000Z", 500),
    _close("2026-10-21T23:59:59.999999Z", 60),
    _fill("2026-10-22T09:00:00.000000Z", 7, 3),
    _close("2026-10-22T00:00:00.000000Z", 250),
    _close("2026-10-22T11:00:00.000000Z", 1000),
    # After NOON_OCT22: excluded by every window pinned to that as_of.
    _fill("2026-10-22T13:00:00.000000Z", 20, 0),
    _close("2026-10-22T14:00:00.000000Z", 4000),
)


@pytest.fixture
def seeded_store(tmp_path: Path) -> LedgerStore:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    for n, (event_type, ts, payload) in enumerate(SEEDED):
        store.append(
            ts_utc=ts,
            source="paper",
            correlation_id=CORR,
            idempotency_key=f"pnl-window-{n:03d}",
            type=event_type,
            payload=payload,
        )
    yield store
    store.close()


@pytest.mark.parametrize(
    ("window", "as_of", "trades", "fees", "realised", "closed"),
    [
        # Today: Oct 22 00:00 through noon. Yesterday's fills and closes are out.
        ("day", NOON_OCT22, 1, 10, 1250, 2),
        # ISO week from Monday Oct 19 through noon Oct 22.
        ("week", NOON_OCT22, 2, 110, 1810, 4),
        ("all", NOON_OCT22, 3, 1110, 10810, 5),
        # Historical as_of: the 23:59:59 close on Oct 21 is after noon and drops out.
        ("day", NOON_OCT21, 0, 0, 500, 1),
        ("week", NOON_OCT21, 1, 100, 500, 1),
        ("all", NOON_OCT21, 2, 1100, 9500, 2),
    ],
    ids=[
        "day-today",
        "week-containing-as_of",
        "all-to-as_of",
        "day-historical-excludes-later-same-day",
        "week-historical",
        "all-historical",
    ],
)
async def test_pnl_folds_only_events_in_window(
    seeded_store: LedgerStore,
    window: str,
    as_of: datetime,
    trades: int,
    fees: int,
    realised: int,
    closed: int,
) -> None:
    out = await run_pnl(
        PnlIn(window=window, as_of=as_of),  # type: ignore[arg-type]
        seeded_store,
        FixtureClock(start=NOON_OCT22.timestamp()),
    )
    assert out["trades"] == trades
    assert out["fees_lamports"] == fees
    assert out["realised_lamports"] == realised
    assert out["closed_trades"] == closed


async def test_pnl_defaults_as_of_to_clock_now(seeded_store: LedgerStore) -> None:
    out = await run_pnl(
        PnlIn(window="day"),
        seeded_store,
        FixtureClock(start=NOON_OCT22.timestamp()),
    )
    assert out["trades"] == 1
    assert out["fees_lamports"] == 10
    assert out["realised_lamports"] == 1250
    assert out["closed_trades"] == 2


async def test_pnl_naive_as_of_is_read_as_utc(seeded_store: LedgerStore) -> None:
    out = await run_pnl(
        PnlIn(window="day", as_of=NOON_OCT22.replace(tzinfo=None)),
        seeded_store,
        FixtureClock(start=0.0),
    )
    assert out["realised_lamports"] == 1250
    assert out["closed_trades"] == 2
