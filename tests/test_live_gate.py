"""Live gate ids and the refusing adapter stub (R21, INV-C-03, FOUND-005)."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from pumpgrok.core.errors import LiveGateError
from pumpgrok.core.ids import IdFactory
from pumpgrok.execution.live import PRECONDITION_IDS, LiveAdapterStub, LiveGate, refusal_lines
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng

EPOCH_START = 1767225600.0  # 2026-01-01T00:00:00Z
NOW = "2026-10-20T00:00:00Z"


def test_gate_reports_nine_ids_in_order(tmp_path: Path) -> None:
    gate = LiveGate(mode="live", environ={}, root=tmp_path)
    evaluated = gate.evaluate(now=NOW)
    assert tuple(item.id for item in evaluated) == PRECONDITION_IDS
    assert [item.number for item in evaluated] == list(range(1, 10))
    # R21/D4: row 1 needs [live] enabled=true; the mode flag alone leaves it unmet.
    assert evaluated[0].met is False
    assert evaluated[0].reason == "effective mode is live but [live] enabled is not true"
    assert gate.check(now=NOW) == list(PRECONDITION_IDS)
    enabled = LiveGate(mode="live", environ={}, root=tmp_path, live_enabled=True)
    assert enabled.evaluate(now=NOW)[0].met is True
    assert "mode_live" not in enabled.check(now=NOW)


def test_precondition_two_is_met_only_by_exact_env_value(tmp_path: Path) -> None:
    gate = LiveGate(mode="live", environ={"PUMPGROK_LIVE_ENABLE": "1"}, root=tmp_path)
    assert gate.evaluate(now=NOW)[1].met is True
    assert "live_enable_env" not in gate.check(now=NOW)
    other = LiveGate(mode="live", environ={"PUMPGROK_LIVE_ENABLE": "yes"}, root=tmp_path)
    assert other.evaluate(now=NOW)[1].met is False


def test_paper_mode_fails_precondition_one(tmp_path: Path) -> None:
    gate = LiveGate(mode="paper", environ={"PUMPGROK_LIVE_ENABLE": "1"}, root=tmp_path)
    assert gate.check(now=NOW)[0] == "mode_live"


def test_refusal_block_lists_each_unmet_id(tmp_path: Path) -> None:
    lines = refusal_lines(LiveGate(mode="live", environ={}, root=tmp_path).evaluate(now=NOW))
    assert lines[0].startswith("LIVE GATE: refusing to start in mode=live. 9 of 9")
    assert any(line.startswith("  [ ] 8 adapter_registered ") for line in lines)
    assert any(line.startswith("  [ ] 1 mode_live ") for line in lines)


def test_adapter_stub_records_then_refuses_every_method(tmp_path: Path) -> None:
    ledger = LedgerStore(tmp_path / "ledger.sqlite")
    clock = FixtureClock(start=EPOCH_START)
    adapter = LiveAdapterStub(
        gate=LiveGate(mode="live", environ={}, root=tmp_path),
        ledger=ledger,
        clock=clock,
        ids=IdFactory(clock, make_rng()),
    )
    with pytest.raises(LiveGateError) as refused:
        asyncio.run(adapter.positions())
    assert "adapter_registered" in refused.value.fields["unmet"]
    with pytest.raises(LiveGateError):
        asyncio.run(adapter.cancel("order", "SOL-20260101-001", "decision"))

    conn = sqlite3.connect(tmp_path / "ledger.sqlite")
    try:
        rows = conn.execute(
            "SELECT source, payload_json FROM events WHERE type='LiveWriteAttempted' ORDER BY seq"
        ).fetchall()
    finally:
        conn.close()
    methods = [json.loads(str(payload))["method"] for _, payload in rows]
    assert methods == ["positions", "cancel"]
    assert {source for source, _ in rows} == {"manual"}
    assert ledger.verify() is True
    ledger.close()
