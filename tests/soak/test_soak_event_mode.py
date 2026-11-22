"""OBS-06 D-06: nightly event-mode soak with zero idle Grok calls and a golden hash.

Runs only under PUMPGROK_REQUIRE_SOAK=1 with -m slow; the default fast path
never picks it up. The event desk runs on recorded source traffic with no
admitted candidates; the idle-zero-Grok invariant is asserted together with
a golden hash of the drain.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
from pathlib import Path

import pytest

from pumpgrok.core.adapter import ExecutionMode
from pumpgrok.events.drain import drain
from pumpgrok.events.models import Event, EventKind
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.event_desk import build_event_desk

pytestmark = [pytest.mark.slow]

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "replay" / "smoke" / "events.jsonl"

# Golden hash of the smoke drain (recorded after first soak run).
GOLDEN_DRAIN_HASH = "c5871bc0c40361aa3e0425a9745764f3787f70b0537f001f2c48b1e7762b6335"


def _require_soak() -> None:
    if os.environ.get("PUMPGROK_REQUIRE_SOAK") != "1":
        pytest.skip("soak requires PUMPGROK_REQUIRE_SOAK=1 with -m slow")


def _events() -> list[Event]:
    rows = [
        json.loads(line)
        for line in FIXTURE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    events: list[Event] = []
    for row in rows:
        try:
            kind = EventKind(row["kind"]) if row["kind"] != "tick" else EventKind.curve_tick
        except (ValueError, KeyError):
            kind = EventKind.curve_tick
        payload = {k: v for k, v in row.items() if k not in {"kind", "mint", "ts_utc"}}
        events.append(
            Event(
                kind=kind,
                entity_id=str(row.get("mint", "x")),
                payload=payload,
                occurred_at=str(row.get("ts_utc", "2026-01-01T00:00:00.000000Z")),
            )
        )
    return events


def test_event_mode_soak_zero_idle_grok(tmp_path: Path) -> None:
    _require_soak()
    assert FIXTURE.is_file(), "smoke fixture missing under PUMPGROK_REQUIRE_SOAK=1"
    events = _events()
    clock = FixtureClock(start=0.0)
    rng = random.Random(20260101)
    drained = drain(events, clock, rng)
    digest = hashlib.sha256(bytes(drained)).hexdigest()
    assert digest == GOLDEN_DRAIN_HASH, f"drain hash moved: {digest}"

    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", "10000000000")
    store.set_meta("source", "paper")
    desk = build_event_desk(
        mode=ExecutionMode.PAPER,
        store=store,
        clock=clock,
        place=lambda intent: None,
        sidecar_path=tmp_path / "sidecar.sqlite",
        params={"momentum_breakout": {"breakout_bps": 100}},
    )
    clock.jump(24 * 3600.0)
    assert desk.gateway.transport_calls == 0
