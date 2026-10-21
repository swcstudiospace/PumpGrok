"""Characterization: position watcher (STRUCT-003).

Pins ``engine/watcher.py`` against the watcher half of
``vendor/grokbot-pumpfun/tests/test_risk.py`` (vendor oracle, kept
byte-identical per R53).

Divergences from the oracle (deliberate):

- The watcher takes a ``PositionBook`` Protocol (positions, exit config,
  poll interval, persist), not a ``RiskManager``. Tests use a double;
  Phase 4 implements the real book.
- ``check_once`` takes ``now`` explicitly; the poll loop sleeps on the
  injected clock.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from pumpgrok.config.settings import ExitsSettings
from pumpgrok.engine.exits import ExitSignal
from pumpgrok.engine.models import ExitPosition
from pumpgrok.engine.watcher import PositionBook, PositionWatcher
from pumpgrok.replay.clock import FixtureClock

NOW = 1_700_000_000.0


def position(
    mint: str = "M",
    entry: float = 1.0,
    sol: float = 0.5,
    peak: float | None = None,
    opened_at: float = 0.0,
) -> ExitPosition:
    return ExitPosition(
        mint=mint,
        entry_price=entry,
        sol_spent=sol,
        opened_at=opened_at,
        peak_price=entry if peak is None else peak,
    )


def exits(**overrides: Any) -> ExitsSettings:
    base: dict[str, Any] = {
        "stop_loss_pct": 30.0,
        "take_profit_pct": 120.0,
        "trailing_stop_pct": 35.0,
        "max_hold_seconds": 3600.0,
        "stop_loss_poll_seconds": 15.0,
    }
    base.update(overrides)
    return ExitsSettings(**base)


class FakeBook:
    """Test-double PositionBook: dict positions, counted persists."""

    def __init__(self, cfg: ExitsSettings) -> None:
        self._positions: dict[str, ExitPosition] = {}
        self._cfg = cfg
        self._poll = cfg.stop_loss_poll_seconds
        self.persisted = 0

    @property
    def positions(self) -> dict[str, ExitPosition]:
        return self._positions

    @property
    def exit_config(self) -> ExitsSettings:
        return self._cfg

    @property
    def poll_seconds(self) -> float:
        return self._poll

    def persist(self) -> None:
        self.persisted += 1

    def add(self, pos: ExitPosition) -> None:
        self._positions[pos.mint] = pos


def test_fake_book_satisfies_protocol() -> None:
    assert isinstance(FakeBook(exits()), PositionBook)


def test_watcher_sells_only_dumped_positions() -> None:
    book = FakeBook(exits())
    book.add(position("DUMP", entry=1.0))
    book.add(position("FINE", entry=1.0))
    prices = {"DUMP": 0.6, "FINE": 1.5}
    sold: list[tuple[str, float, str]] = []

    async def price_fn(mint: str) -> float:
        return prices[mint]

    async def sell_fn(pos: ExitPosition, price: float, reason: str) -> None:
        sold.append((pos.mint, price, reason))
        del book.positions[pos.mint]

    watcher = PositionWatcher(book, price_fn, sell_fn, FixtureClock())
    triggered = asyncio.run(watcher.check_once(NOW))
    assert triggered == ["DUMP"]
    assert sold == [("DUMP", 0.6, "stop_loss")]
    assert "FINE" in book.positions
    assert "DUMP" not in book.positions


def test_watcher_survives_price_errors() -> None:
    book = FakeBook(exits())
    book.add(position("A", entry=1.0))

    async def price_fn(mint: str) -> float:
        raise ConnectionError("no quote")

    async def sell_fn(pos: ExitPosition, price: float, reason: str) -> None:
        raise AssertionError("must not sell without a price")

    watcher = PositionWatcher(book, price_fn, sell_fn, FixtureClock())
    assert asyncio.run(watcher.check_once(NOW)) == []
    assert "A" in book.positions
    assert watcher.price_failures == {"A": 1}


def test_watcher_tracks_peak_and_persists() -> None:
    book = FakeBook(exits())
    book.add(position("A", entry=1.0, opened_at=NOW - 10))

    async def price_fn(mint: str) -> float:
        return 1.5

    async def sell_fn(pos: ExitPosition, price: float, reason: str) -> None:
        raise AssertionError("1.5 is neither take-profit nor trailing")

    watcher = PositionWatcher(book, price_fn, sell_fn, FixtureClock())
    assert asyncio.run(watcher.check_once(NOW)) == []
    assert book.positions["A"].peak_price == pytest.approx(1.5)
    assert book.persisted == 1  # peak survived a restart


def test_small_peak_step_does_not_persist() -> None:
    book = FakeBook(exits())
    book.add(position("A", entry=1.0, opened_at=NOW - 10))

    async def price_fn(mint: str) -> float:
        return 1.005  # below PEAK_PERSIST_STEP

    async def sell_fn(pos: ExitPosition, price: float, reason: str) -> None:
        raise AssertionError("must not sell")

    watcher = PositionWatcher(book, price_fn, sell_fn, FixtureClock())
    assert asyncio.run(watcher.check_once(NOW)) == []
    assert book.positions["A"].peak_price == pytest.approx(1.005)
    assert book.persisted == 0


def test_watcher_reports_exit_reason() -> None:
    book = FakeBook(exits())
    book.add(position("A", entry=1.0, opened_at=NOW - 10))
    seen: list[str] = []

    async def price_fn(mint: str) -> float:
        return 2.5

    async def sell_fn(pos: ExitPosition, price: float, reason: str) -> None:
        seen.append(reason)
        del book.positions[pos.mint]

    watcher = PositionWatcher(book, price_fn, sell_fn, FixtureClock())
    assert asyncio.run(watcher.check_once(NOW)) == ["A"]
    assert seen == ["take_profit"]
    assert isinstance(ExitSignal(reason=seen[0]), ExitSignal)


def test_position_without_price_is_reported_blind() -> None:
    book = FakeBook(exits())
    book.add(position("A", entry=1.0))

    async def price_fn(mint: str) -> float:
        raise ConnectionError("no quote")

    async def sell_fn(pos: ExitPosition, price: float, reason: str) -> None:
        raise AssertionError("must not sell")

    watcher = PositionWatcher(book, price_fn, sell_fn, FixtureClock())
    for _ in range(2):
        assert asyncio.run(watcher.check_once(NOW)) == []
        assert watcher.blind == []
    assert asyncio.run(watcher.check_once(NOW)) == []
    assert watcher.blind == ["A"]


def test_zero_price_counts_as_missing() -> None:
    book = FakeBook(exits())
    book.add(position("A", entry=1.0))

    async def price_fn(mint: str) -> float:
        return 0.0

    async def sell_fn(pos: ExitPosition, price: float, reason: str) -> None:
        raise AssertionError("must not sell")

    watcher = PositionWatcher(book, price_fn, sell_fn, FixtureClock())
    for _ in range(3):
        asyncio.run(watcher.check_once(NOW))
    assert watcher.blind == ["A"]


def test_recovered_price_clears_blindness() -> None:
    book = FakeBook(exits())
    book.add(position("A", entry=1.0, opened_at=NOW - 10))
    quotes = [0.0, 0.0, 1.1]

    async def price_fn(mint: str) -> float:
        return quotes.pop(0) if quotes else 1.1

    async def sell_fn(pos: ExitPosition, price: float, reason: str) -> None:
        raise AssertionError("must not sell")

    watcher = PositionWatcher(book, price_fn, sell_fn, FixtureClock())
    asyncio.run(watcher.check_once(NOW))
    asyncio.run(watcher.check_once(NOW))
    assert watcher.blind == []
    asyncio.run(watcher.check_once(NOW))
    assert "A" not in watcher.price_failures


def test_closed_position_is_not_blind() -> None:
    book = FakeBook(exits())
    book.add(position("A", entry=1.0))

    async def price_fn(mint: str) -> float:
        raise ConnectionError("no quote")

    async def sell_fn(pos: ExitPosition, price: float, reason: str) -> None:
        raise AssertionError("must not sell")

    watcher = PositionWatcher(book, price_fn, sell_fn, FixtureClock())
    for _ in range(3):
        asyncio.run(watcher.check_once(NOW))
    assert watcher.blind == ["A"]
    del book.positions["A"]
    assert watcher.blind == []
