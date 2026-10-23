"""Serve ticks evaluate the exit rules too: a take-profit closes the position on a tick.

Same injected fixture clock and FixtureCurveSource as replay, no network source.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pumpgrok.config.settings import FilterSettings
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.fixtures import load_dataset
from pumpgrok.supervisor.scheduler import build_serve_replay, dataset_events_start

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "tests" / "fixtures" / "replay" / "smoke"
SEED = 20260101
MINT = "SmokeMintBBBB2222222222222222222222222222222"
# Offsets from the first fixture stamp. The sniper polls once a second and the exit seat
# once every 15 s, so these ticks reach each candidate at its own fixture time and the
# 30 s curve tick where the exit rule fires.
SERVE_OFFSETS = (0.0, 1.25, 2.5, 3.5, 30.0, 31.0)


async def _serve_ticks(supervisor: Any, clock: FixtureClock, start: float) -> None:
    for offset in SERVE_OFFSETS:
        if start + offset > clock.now():
            clock.advance_to(start + offset)
        await supervisor.tick_once()


def test_serve_tick_closes_the_position_on_take_profit(tmp_path: Path) -> None:
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
        rows = store.read(limit=None)
    finally:
        store.close()
    closed = [row for row in rows if row["type"] == "PositionClosed"]
    assert [row["payload"]["reason"] for row in closed] == ["take_profit"]
    assert closed[0]["payload"]["mint"] == MINT
    sells = [
        row for row in rows if row["type"] == "FillRecorded" and row["payload"]["side"] == "sell"
    ]
    assert [row["payload"]["mint"] for row in sells] == [MINT]
