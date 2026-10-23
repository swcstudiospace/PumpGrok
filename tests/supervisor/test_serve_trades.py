"""Serve mode trades like replay: the sniper places granted paper buys, and the exit seat sells.

A serve loop over the smoke fixture, driven by the same injected fixture clock and
FixtureCurveSource that replay uses, must write the same order rows as the one-shot
replay cycle. No network source is touched.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pumpgrok.config.settings import FilterSettings
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.fixtures import load_dataset
from pumpgrok.supervisor.scheduler import (
    build_serve_replay,
    dataset_events_start,
    run_once_replay,
)

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "tests" / "fixtures" / "replay" / "smoke"
SEED = 20260101
GRADUATED_MINT = "SmokeMintBBBB2222222222222222222222222222222"
# Offsets from the first fixture stamp: the sniper polls once a second and the exit seat
# every 15 s, so these ticks reach each candidate at its own fixture time (the 3.0 s
# candidate at the 3.5 s poll) and the 30 s curve tick where the exit rule fires.
SERVE_OFFSETS = (0.0, 1.25, 2.5, 3.5, 30.0, 31.0)


async def _serve_ticks(supervisor: Any, clock: FixtureClock, start: float) -> None:
    """One serve tick per offset; the clock only moves forward."""
    for offset in SERVE_OFFSETS:
        if start + offset > clock.now():
            clock.advance_to(start + offset)
        await supervisor.tick_once()


def _order_shape(rows: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    shape: list[tuple[Any, ...]] = []
    for row in rows:
        payload = row["payload"]
        if row["type"] == "FillRecorded":
            shape.append((row["type"], payload["side"], payload["mint"]))
        elif row["type"] in ("OrderRejected", "PositionClosed"):
            shape.append((row["type"], payload["reason"]))
        else:
            shape.append((row["type"],))
    return shape


def test_serve_tick_writes_the_same_order_rows_as_replay(tmp_path: Path) -> None:
    replay_ledger = tmp_path / "replay.sqlite"
    run_once_replay(SMOKE, FilterSettings(), seed=SEED, ledger_path=replay_ledger)
    replay_store = LedgerStore(str(replay_ledger))
    try:
        replay_rows = replay_store.read(limit=None)
    finally:
        replay_store.close()

    start = dataset_events_start(load_dataset(SMOKE))
    clock = FixtureClock(start=start)
    supervisor, _metrics, store = build_serve_replay(
        SMOKE,
        FilterSettings(),
        seed=SEED,
        clock=clock,
        ledger_path=tmp_path / "serve.sqlite",
    )
    try:
        asyncio.run(_serve_ticks(supervisor, clock, start))
        serve_rows = store.read(limit=None)
    finally:
        store.close()

    assert _order_shape(serve_rows) == _order_shape(replay_rows)
    fills = [row for row in serve_rows if row["type"] == "FillRecorded"]
    assert [(row["payload"]["side"], row["payload"]["mint"]) for row in fills] == [
        ("buy", GRADUATED_MINT),
        ("sell", GRADUATED_MINT),
    ]
    assert len([row for row in serve_rows if row["type"] == "PositionOpened"]) == 1
    closed = [row["payload"]["reason"] for row in serve_rows if row["type"] == "PositionClosed"]
    assert closed == ["take_profit"]
