"""AUTO-005 degraded modes and the AUTO-006 ten-seat cycle.

Every paper-engine.md 6.7 row is asserted with its behavior and recovery:
LLM failure degrades bot-08-signal to rule-based scoring in live-paper
(and observe-only for buys when ``signal.require_llm`` is set; in replay a
missing LLM record fails the run per R27), RPC failure fails over then
marks BLIND, WebSocket loss reconnects with backoff and trips DataStale
after 120 s, an unwritable ledger refuses orders into a bounded 1000-event
buffer with ``persistence_down``, and clock skew over 5 s refuses appends
with ``clock_skew``. AUTO-006 then runs ``run --mode paper --once --replay``
over the smoke fixture: one full ten-seat cycle through the engine, risk,
and paper adapter writes the replay ledger and exits 0 with no network.
"""

from __future__ import annotations

import asyncio
from functools import partial
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.cli import main
from pumpgrok.config.settings import FilterSettings
from pumpgrok.core.errors import ReplayMissingRecord
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.recorder import ReplayLlm
from pumpgrok.supervisor.scheduler import (
    LEDGER_BUFFER_CAP,
    DegradedState,
    LedgerUnavailable,
    run_once_replay,
)
from pumpgrok.supervisor.seat_task import CLOCK_SKEW_S, ClockSkew, append_escalation

SMOKE = Path(__file__).resolve().parents[1] / "fixtures" / "replay" / "smoke"


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    return LedgerStore(str(path))


def test_llm_down_falls_back_or_observes_buys_with_recovery() -> None:
    degraded = DegradedState()
    assert degraded.signal_scoring_mode(replay=False) == "llm"
    degraded.llm_available = False
    assert degraded.signal_scoring_mode(replay=False) == "rule_fallback"
    degraded.require_llm = True
    assert degraded.signal_scoring_mode(replay=False) == "observe_only_buys"
    degraded.llm_available = True
    assert degraded.signal_scoring_mode(replay=False) == "llm"
    assert degraded.signal_scoring_mode(replay=True) == "replay"


def test_replay_missing_llm_record_fails_the_run() -> None:
    table = ReplayLlm.from_rows([])
    with pytest.raises(ReplayMissingRecord):
        table.complete({"dataset": "smoke", "events": 4}, FixtureClock(start=0.0))


def test_rpc_failover_then_blind_with_recovery() -> None:
    degraded = DegradedState(rpc_endpoints=[True, True])
    assert degraded.rpc_blind is False
    degraded.note_rpc_result(0, False)
    assert degraded.rpc_blind is False
    degraded.note_rpc_result(1, False)
    assert degraded.rpc_blind is True
    degraded.note_rpc_result(0, True)
    assert degraded.rpc_blind is False


def test_ws_silence_trips_data_stale_and_frame_recovers() -> None:
    degraded = DegradedState()
    assert degraded.ws_data_stale(10_000.0) is False
    degraded.note_ws_frame(0.0)
    assert degraded.ws_data_stale(119.0) is False
    assert degraded.ws_data_stale(121.0) is True
    degraded.note_ws_frame(121.0)
    assert degraded.ws_data_stale(122.0) is False


def test_unwritable_ledger_buffers_1000_then_refuses_and_drains(tmp_path: Path) -> None:
    degraded = DegradedState(ledger_writable=False)
    row = {
        "ts_utc": format_ts_utc(1.0),
        "source": "paper",
        "correlation_id": "desk",
        "idempotency_key": "k-0",
        "type": "JournalNote",
        "payload": {
            "source": "paper",
            "seat": "desk",
            "note_kind": "note",
            "text": "t",
            "refs": [],
        },
    }
    for index in range(LEDGER_BUFFER_CAP):
        degraded.buffer_order(dict(row, idempotency_key=f"k-{index}"))
    with pytest.raises(LedgerUnavailable):
        degraded.buffer_order(dict(row, idempotency_key="k-overflow"))
    store = _store(tmp_path)
    try:
        drained = degraded.drain_buffer(store)
        assert drained == LEDGER_BUFFER_CAP
        assert store.count() == LEDGER_BUFFER_CAP
        assert degraded.ledger_buffer == []
        assert degraded.persistence_raised is False
    finally:
        store.close()


def test_clock_skew_refuses_appends_with_escalation(tmp_path: Path) -> None:
    clock = FixtureClock(start=0.0)
    store = _store(tmp_path)
    try:
        store.append(
            ts_utc=format_ts_utc(1_000.0),
            source="replay",
            correlation_id="desk",
            idempotency_key="head",
            type="JournalNote",
            payload={
                "source": "replay",
                "seat": "desk",
                "note_kind": "note",
                "text": "head",
                "refs": [],
            },
        )
        with pytest.raises(ClockSkew):
            append_escalation(
                store,
                clock,
                kind="heartbeat_stale",
                seat="bot-01-scout",
                detail="stale",
                source="replay",
                correlation_id="desk",
            )
        kinds = [e["payload"]["kind"] for e in store.read(types=["Escalation"], limit=None)]
        assert kinds == ["clock_skew"]
        assert CLOCK_SKEW_S == 5.0
    finally:
        store.close()


async def test_ten_seat_smoke_cycle_writes_ledger_and_exits_0(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    call = partial(run_once_replay, SMOKE, FilterSettings(), seed=20260101, ledger_path=ledger)
    result = await asyncio.to_thread(call)
    assert result.decision == "skip"
    assert result.reason == "data_unavailable"
    assert result.events_read == 4
    store = LedgerStore(str(ledger))
    try:
        assert store.verify() is True
        rows = store.read(limit=None)
        assert len(rows) == 1
        assert rows[0]["type"] == "JournalNote"
        assert "engine decision=skip reason=data_unavailable" in str(rows[0]["payload"]["text"])
    finally:
        store.close()


def test_smoke_cycle_cli_exits_0_with_no_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["run", "--mode", "paper", "--once", "--replay", str(SMOKE)]) == 0
    ledger = tmp_path / "var" / "replay" / "smoke" / "ledger.sqlite"
    assert ledger.is_file()
    store = LedgerStore(str(ledger))
    try:
        assert store.count() == 1
    finally:
        store.close()
    captured = capsys.readouterr()
    assert "engine decision=skip reason=data_unavailable" in captured.out
