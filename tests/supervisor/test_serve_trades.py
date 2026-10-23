"""Serve mode trades like replay: the sniper places granted paper buys, and the exit seat sells.

A serve over the smoke fixture follows the recorded timeline through the same driver
(:func:`serve_fixture_timeline`) that serve uses in production, on the injected fixture
clock and FixtureCurveSource. It must write the same order rows as the one-shot replay.
Serve also records ``heartbeat_stale`` escalations when a seat misses its cadence across
a recording gap; those are health rows, not orders, so the comparison leaves them out.
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
    dataset_stamps,
    run_once_replay,
    serve_fixture_timeline,
)

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "tests" / "fixtures" / "replay" / "smoke"
SEED = 20260101
GRADUATED_MINT = "SmokeMintBBBB2222222222222222222222222222222"


def _order_shape(rows: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    shape: list[tuple[Any, ...]] = []
    for row in rows:
        if row["type"] == "Escalation":
            continue
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

    stamps = dataset_stamps(load_dataset(SMOKE))
    clock = FixtureClock(start=stamps[0])
    supervisor, _metrics, store = build_serve_replay(
        SMOKE,
        FilterSettings(),
        seed=SEED,
        clock=clock,
        ledger_path=tmp_path / "serve.sqlite",
    )
    try:
        asyncio.run(serve_fixture_timeline(supervisor, stamps, heartbeats=True))
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
