"""Daily report strategy fills: attribution, windowing and win stats."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from pumpgrok.backtest.roundtrip import RoundTripFill, group_round_trips
from pumpgrok.reporting.daily import (
    _inclusive_days,
    _strategy_fills,
    _strategy_section,
    _strategy_win_stats,
    day_next,
    day_start,
)

START = "2026-01-01T00:00:00Z"
END = "2026-01-02T00:00:00Z"
REFS = {"t1": "momentum_breakout", "t2": "mean_reversion"}


def _ev(seq: int, typ: str, ts: str, payload: Any) -> dict[str, Any]:
    return {"seq": seq, "type": typ, "ts_utc": ts, "payload": payload}


def test_fills_attribute_to_the_ticket_strategy() -> None:
    events = [
        _ev(1, "PositionOpened", START, {"ticket_id": "t1", "mint": "M1"}),
        _ev(
            2,
            "FillRecorded",
            "2026-01-01T01:00:00Z",
            {"side": "buy", "mint": "M1", "cash_delta_lamports": -100},
        ),
        _ev(
            3,
            "FillRecorded",
            "2026-01-01T02:00:00Z",
            {"side": "sell", "mint": "M1", "cash_delta_lamports": 130},
        ),
        _ev(4, "PositionOpened", "2026-01-01T03:00:00Z", {"ticket_id": "t2", "mint": "M2"}),
        _ev(
            5,
            "FillRecorded",
            "2026-01-01T04:00:00Z",
            {"side": "buy", "mint": "M2", "cash_delta_lamports": -200},
        ),
    ]
    fills = _strategy_fills(events, REFS, START, END)
    by_strategy = {}
    for fill in fills:
        by_strategy.setdefault(fill.strategy_id, []).append(fill)
    assert by_strategy["momentum_breakout"][0].key == "M1"
    assert by_strategy["mean_reversion"][0].key == "M2"
    assert all(f.strategy_id in REFS.values() for f in fills)


def test_fills_skip_outside_window_and_bad_sides() -> None:
    events = [
        _ev(
            1,
            "FillRecorded",
            "2025-12-31T23:00:00Z",
            {"side": "buy", "mint": "M1", "cash_delta_lamports": -1},
        ),
        _ev(
            2,
            "FillRecorded",
            "2026-01-01T01:00:00Z",
            {"side": "hold", "mint": "M1", "cash_delta_lamports": -1},
        ),
        _ev(
            3,
            "FillRecorded",
            "2026-01-02T00:00:00Z",
            {"side": "buy", "mint": "M1", "cash_delta_lamports": -1},
        ),
        _ev(4, "FillRecorded", "2026-01-01T01:00:00Z", "not a mapping"),
        _ev(5, "PositionOpened", "2026-01-01T01:00:00Z", {"ticket_id": "", "mint": "M1"}),
        _ev(6, "PositionOpened", "2026-01-01T01:00:00Z", {"mint": "M1"}),
    ]
    assert _strategy_fills(events, REFS, START, END) == []


def test_buys_before_the_open_are_attributed_when_it_lands() -> None:
    events = [
        _ev(
            1,
            "FillRecorded",
            "2026-01-01T01:00:00Z",
            {"side": "buy", "mint": "M1", "cash_delta_lamports": -100},
        ),
        _ev(
            2,
            "FillRecorded",
            "2026-01-01T02:00:00Z",
            {"side": "sell", "mint": "M1", "cash_delta_lamports": 90},
        ),
        _ev(3, "PositionOpened", "2026-01-01T03:00:00Z", {"ticket_id": "t1", "mint": "M1"}),
    ]
    fills = _strategy_fills(events, REFS, START, END)
    # Pending buys are re-attributed when the open lands; sells recorded before
    # the open stay unattributed (fills are keyed only by buys).
    by_side = {fill.side: fill for fill in fills}
    assert by_side["buy"].strategy_id == "momentum_breakout"
    assert by_side["sell"].strategy_id == "unattributed"


def test_win_stats_count_only_closed_trips() -> None:
    result = group_round_trips(
        [
            RoundTripFill("A", "buy", 100, "s1"),
            RoundTripFill("A", "sell", 130, "s1"),
            RoundTripFill("A", "buy", 100, "s1"),
            RoundTripFill("A", "sell", 80, "s1"),
            RoundTripFill("B", "buy", 50, "s2"),
        ]
    )
    rates, counts = _strategy_win_stats(result)
    assert counts == {"s1": 2}
    assert rates == {"s1": 0.5}


def test_win_stats_with_only_unclosed_trips() -> None:
    result = group_round_trips([RoundTripFill("A", "buy", 100, "s1")])
    assert _strategy_win_stats(result) == ({}, {})


def test_day_helpers() -> None:
    assert day_start("2026-01-01") == "2026-01-01T00:00:00.000000Z"
    assert day_next("2026-01-01") == "2026-01-02T00:00:00.000000Z"
    assert _inclusive_days("2026-01-01", "2026-01-01") == 1
    assert _inclusive_days("2026-01-01", "2026-01-03") == 3
    try:
        _inclusive_days("2026-01-03", "2026-01-01")
    except ValueError as exc:
        assert "calendar range" in str(exc)
    else:
        raise AssertionError("backwards span accepted")


def _ledger_with_refs(tmp_path: Path) -> Path:

    path = tmp_path / "ledger.sqlite"
    db = sqlite3.connect(str(path))
    db.execute("CREATE TABLE strategy_ticket_refs (ticket_id TEXT, strategy_id TEXT)")
    db.execute("INSERT INTO strategy_ticket_refs VALUES ('t1', 'momentum_breakout')")
    db.commit()
    db.close()
    return path


def test_strategy_section_round_trips_through_the_ledger(tmp_path: Path) -> None:
    ledger = _ledger_with_refs(tmp_path)
    events = [
        _ev(1, "PositionOpened", START, {"ticket_id": "t1", "mint": "M1"}),
        _ev(
            2,
            "FillRecorded",
            "2026-01-01T01:00:00Z",
            {"side": "buy", "mint": "M1", "cash_delta_lamports": -100},
        ),
        _ev(
            3,
            "FillRecorded",
            "2026-01-01T02:00:00Z",
            {"side": "sell", "mint": "M1", "cash_delta_lamports": 130},
        ),
    ]
    section = _strategy_section(ledger, events, "2026-01-01", "2026-01-01")
    assert "momentum_breakout" in section


def test_strategy_section_empty_without_refs(tmp_path: Path) -> None:
    assert _strategy_section(tmp_path / "missing.sqlite", [], "2026-01-01", "2026-01-01") == ""
