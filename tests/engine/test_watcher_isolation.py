"""Regression tests for the position watcher: sell isolation, quote misses, log scale.

Covers ENG-02 (one failing sell must not stop the other positions and must not
skip the persist), WATCH-01 (exit log shows the scaled price in real units) and
the watcher half of ENG-01 (no quote is a miss, a real zero is a quote).
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import pytest

import pumpgrok.engine.watcher as watcher_module
from pumpgrok.config.settings import ExitsSettings
from pumpgrok.engine.models import PRICE_SCALE, ExitPosition
from pumpgrok.engine.watcher import PositionBook, PositionWatcher
from pumpgrok.replay.clock import FixtureClock

NOW = 1_700_000_000.0


def _px(value: float) -> int:
    """Test shorthand price to the integer ``PRICE_SCALE`` price (INT-01)."""
    return int((Decimal(str(value)) * PRICE_SCALE).to_integral_value(rounding=ROUND_HALF_UP))


def _lamports(sol: float) -> int:
    return int((Decimal(str(sol)) * 1_000_000_000).to_integral_value(rounding=ROUND_HALF_UP))


def position(mint: str, entry: float = 1.0) -> ExitPosition:
    # opened_at is recent: a position opened at 0.0 would hit max_hold at once.
    return ExitPosition(
        mint=mint,
        entry_price=_px(entry),
        sol_spent=_lamports(0.5),
        opened_at=NOW - 10,
        peak_price=_px(entry),
    )


def exits() -> ExitsSettings:
    return ExitsSettings(
        stop_loss_pct=30.0,
        take_profit_pct=120.0,
        trailing_stop_pct=35.0,
        max_hold_seconds=3600.0,
        stop_loss_poll_seconds=15.0,
    )


class FakeBook:
    """Test-double PositionBook: dict positions, counted persists."""

    def __init__(self) -> None:
        self._positions: dict[str, ExitPosition] = {}
        self._cfg = exits()
        self.persisted = 0

    @property
    def positions(self) -> dict[str, ExitPosition]:
        return self._positions

    @property
    def exit_config(self) -> ExitsSettings:
        return self._cfg

    @property
    def poll_seconds(self) -> float:
        return self._cfg.stop_loss_poll_seconds

    def persist(self) -> None:
        self.persisted += 1

    def add(self, pos: ExitPosition) -> None:
        self._positions[pos.mint] = pos


def _feed(prices: dict[str, int | None]) -> Any:
    async def price_fn(mint: str) -> int | None:
        return prices[mint]

    return price_fn


def test_fake_book_satisfies_protocol() -> None:
    assert isinstance(FakeBook(), PositionBook)


async def test_one_failing_sell_does_not_stop_the_other_positions() -> None:
    book = FakeBook()
    book.add(position("A"))
    book.add(position("B"))
    sold: list[str] = []

    async def sell_fn(pos: ExitPosition, price: int, reason: str) -> None:
        if pos.mint == "A":
            raise RuntimeError("venue down")
        sold.append(pos.mint)
        del book.positions[pos.mint]

    watcher = PositionWatcher(book, _feed({"A": _px(0.6), "B": _px(0.6)}), sell_fn, FixtureClock())
    triggered = await watcher.check_once(NOW)

    assert triggered == ["B"]
    assert sold == ["B"]
    assert "A" in book.positions
    assert book.persisted == 1


async def test_peak_persists_even_when_a_later_sell_raises() -> None:
    book = FakeBook()
    book.add(position("A"))
    book.add(position("B"))

    async def sell_fn(pos: ExitPosition, price: int, reason: str) -> None:
        raise RuntimeError("venue down")

    # A rises (peak to 1.5, no exit); B's sell then fails.
    watcher = PositionWatcher(book, _feed({"A": _px(1.5), "B": _px(0.6)}), sell_fn, FixtureClock())
    assert await watcher.check_once(NOW) == []

    assert book.positions["A"].peak_price == _px(1.5)
    assert book.persisted == 1


async def test_zero_price_is_a_quote_not_a_miss() -> None:
    book = FakeBook()
    book.add(position("A"))
    quotes: list[int | None] = [None, None, None, 0]

    async def price_fn(mint: str) -> int | None:
        return quotes.pop(0)

    async def sell_fn(pos: ExitPosition, price: int, reason: str) -> None:
        pass

    watcher = PositionWatcher(book, price_fn, sell_fn, FixtureClock())
    for _ in range(3):
        await watcher.check_once(NOW)
    assert watcher.blind == ["A"]

    await watcher.check_once(NOW)
    assert watcher.blind == []
    assert watcher.price_failures == {}


async def test_zero_price_is_passed_through_to_the_exit_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    book = FakeBook()
    book.add(position("A"))
    seen: list[int] = []

    def record(pos: ExitPosition, price: int, cfg: ExitsSettings, now: float) -> None:
        seen.append(price)
        return None

    monkeypatch.setattr(watcher_module, "apply_price", record)

    async def price_fn(mint: str) -> int | None:
        return 0

    async def sell_fn(pos: ExitPosition, price: int, reason: str) -> None:
        raise AssertionError("no rule fires in this test")

    await PositionWatcher(book, price_fn, sell_fn, FixtureClock()).check_once(NOW)
    assert seen == [0]


async def test_exit_log_shows_prices_in_lamports_per_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    book = FakeBook()
    book.add(position("A", entry=1.0))

    async def sell_fn(pos: ExitPosition, price: int, reason: str) -> None:
        del book.positions[pos.mint]

    caplog.set_level(logging.INFO, logger="pumpgrok.engine.watcher")
    watcher = PositionWatcher(book, _feed({"A": _px(0.6)}), sell_fn, FixtureClock())
    assert await watcher.check_once(NOW) == ["A"]

    assert "entry 1.000000000000, now 0.600000000000" in caplog.text
