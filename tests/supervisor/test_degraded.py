"""AUTO-005 degraded modes and the AUTO-006 ten-seat cycle.

Every paper-engine.md 6.7 row with a production producer is asserted with its behavior and
recovery: LLM failure degrades bot-08-signal to rule-based scoring in live paper, in replay a
missing LLM record fails the run per R27, and an unwritable ledger refuses orders into a
bounded 1000-event buffer. The health body and the metrics read the ledger latches (kill
switch, halt, breakers) and never report ``ok`` while the desk is halted. AUTO-006 then runs
``run --mode paper --once --replay`` over the smoke fixture: one full ten-seat cycle through
the engine, risk, and paper adapter writes the replay ledger and exits 0 with no network.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

import pytest

import pumpgrok.supervisor.scheduler as scheduler_pkg
from pumpgrok.cli import main
from pumpgrok.config.settings import FilterSettings, load_settings
from pumpgrok.core.errors import ReplayMissingRecord
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS, roster_tool_names
from pumpgrok.ledger import operator_choices as oc
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.recorder import ReplayLlm
from pumpgrok.replay.rng import make_rng
from pumpgrok.supervisor.scheduler import (
    LEDGER_BUFFER_CAP,
    ROSTER,
    DegradedState,
    LedgerUnavailable,
    Supervisor,
    kill_switch_engaged,
    rollover_key,
    run_once_replay,
)
from pumpgrok.supervisor.seat_relay import CLOCK_SKEW_S, ClockSkew, append_escalation
from pumpgrok.tools import ensure_paper_genesis

SMOKE = Path(__file__).resolve().parents[1] / "fixtures" / "replay" / "smoke"


AUTHORITY_AT = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


def _record_complete_authority() -> None:
    """Real operator authority for every seat, as the onboarding verbs record it.

    The paper genesis is written first, then the operator key and an HMAC-authenticated
    allow per roster tool, so the paper startup gate reads complete authority inputs.
    """
    oc.init_key(oc.OPERATOR_DIR)
    store = LedgerStore(PAPER_LEDGER_PATH)
    try:
        ensure_paper_genesis(store, load_settings(mode="paper").risk)
        for seat in EXPECTED_SEAT_IDS:
            for tool in sorted(roster_tool_names(oc.DEFAULT_CONTRACTS_DIR, seat)):
                oc.record_tool_choice(
                    store,
                    seat=seat,
                    tool=tool,
                    decision="allow",
                    now=AUTHORITY_AT,
                    operator_dir=oc.OPERATOR_DIR,
                )
    finally:
        store.close()


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    return LedgerStore(str(path))


def test_llm_down_falls_back_with_recovery() -> None:
    degraded = DegradedState()
    assert degraded.signal_scoring_mode(replay=False) == "llm"
    degraded.llm_available = False
    assert degraded.signal_scoring_mode(replay=False) == "rule_fallback"
    degraded.llm_available = True
    assert degraded.signal_scoring_mode(replay=False) == "llm"
    assert degraded.signal_scoring_mode(replay=True) == "replay"


def test_replay_missing_llm_record_fails_the_run() -> None:
    table = ReplayLlm.from_rows([])
    with pytest.raises(ReplayMissingRecord):
        table.complete({"dataset": "smoke", "events": 4}, FixtureClock(start=0.0))


def test_rpc_blind_only_when_every_endpoint_is_down() -> None:
    assert DegradedState(rpc_endpoints=[False, True]).rpc_blind is False
    assert DegradedState(rpc_endpoints=[False, False]).rpc_blind is True
    assert DegradedState(rpc_endpoints=[]).rpc_blind is False


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


def _buffered_row(key: str) -> dict[str, Any]:
    return {
        "ts_utc": format_ts_utc(1.0),
        "source": "paper",
        "correlation_id": "desk",
        "idempotency_key": key,
        "type": "JournalNote",
        "payload": {
            "source": "paper",
            "seat": "desk",
            "note_kind": "note",
            "text": "t",
            "refs": [],
        },
    }


def test_drain_keeps_a_row_whose_append_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    degraded = DegradedState(ledger_writable=False)
    degraded.buffer_order(_buffered_row("k-refused"))
    store = _store(tmp_path)
    try:
        landed_append = store.append

        def _refuse(**_kwargs: Any) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(store, "append", _refuse)
        with pytest.raises(OSError):
            degraded.drain_buffer(store)
        assert [row["idempotency_key"] for row in degraded.ledger_buffer] == ["k-refused"]
        monkeypatch.setattr(store, "append", landed_append)
        assert degraded.drain_buffer(store) == 1
        assert degraded.ledger_buffer == []
        assert store.count() == 1
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
    assert result.decision == "buy"
    assert result.reason == "ok"
    assert result.events_read == 5
    store = LedgerStore(str(ledger))
    try:
        assert store.verify() is True
        rows = store.read(limit=None)
        assert len(rows) == 155
        assert rows[0]["type"] == "JournalNote"
        assert "engine decision=buy reason=ok" in str(rows[0]["payload"]["text"])
        assert [row["type"] for row in rows[2:]] == [
            *["ConfigChanged"] * 143,
            "DailyRollover",
            "OrderRejected",
            "OrderPlaced",
            "FillRecorded",
            "PositionOpened",
            "MarkToMarket",
            "ApprovalRecorded",
            "OrderPlaced",
            "FillRecorded",
            "PositionClosed",
        ]
        rollover = rows[145]
        assert rollover["type"] == "DailyRollover"
        assert rollover["payload"]["day_utc"] == "2026-01-01"
        assert rollover["idempotency_key"] == rollover_key("2026-01-01")
    finally:
        store.close()


def test_smoke_cycle_cli_exits_0_with_no_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    monkeypatch.chdir(tmp_path)
    _record_complete_authority()
    assert main(["run", "--mode", "paper", "--once", "--replay", str(SMOKE)]) == 0
    ledger = tmp_path / "var" / "replay" / "smoke" / "ledger.sqlite"
    assert ledger.is_file()
    store = LedgerStore(str(ledger))
    try:
        assert store.count() == 155
        rows = store.read(limit=None)
        assert [row["type"] for row in rows] == [
            "JournalNote",
            *["ConfigChanged"] * 144,
            "DailyRollover",
            "OrderRejected",
            "OrderPlaced",
            "FillRecorded",
            "PositionOpened",
            "MarkToMarket",
            "ApprovalRecorded",
            "OrderPlaced",
            "FillRecorded",
            "PositionClosed",
        ]
    finally:
        store.close()
    captured = capsys.readouterr()
    assert "engine decision=buy reason=ok" in captured.out
    assert "outcome=filled reason=ok" in captured.out
    assert "trades filled=2 not_filled=1" in captured.out


def test_unwired_probe_surfaces_are_removed() -> None:
    """DESK-D-21/22: nothing fed these switches or setters, so they are deleted, not exposed."""
    with pytest.raises(TypeError):
        DegradedState(require_llm=True)  # type: ignore[call-arg]
    for name in ("note_rpc_result", "note_ws_frame", "ws_data_stale", "skew_detected"):
        assert not hasattr(DegradedState, name)
    assert not hasattr(scheduler_pkg, "assert_no_skew")
    assert not hasattr(scheduler_pkg, "WS_STALE_S")


def test_kill_switch_probe_folds_only_rows_appended_since_the_last_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PUMPGROK_KILLSWITCH", raising=False)
    store = _store(tmp_path)
    try:
        store.append(
            ts_utc=format_ts_utc(1.0),
            source="replay",
            correlation_id="desk",
            idempotency_key="kill-set",
            type="KillSwitchSet",
            payload={"source": "replay", "origin": "tool", "reason": "test"},
        )
        assert kill_switch_engaged(store) is True
        store.append(
            ts_utc=format_ts_utc(2.0),
            source="replay",
            correlation_id="desk",
            idempotency_key="kill-clear",
            type="KillSwitchCleared",
            payload={"source": "replay", "cleared_by": "human:test"},
        )
        since: list[Any] = []
        real_read = store.read

        def _recording_read(**kwargs: Any) -> list[dict[str, Any]]:
            since.append(kwargs.get("since_seq"))
            return real_read(**kwargs)

        monkeypatch.setattr(store, "read", _recording_read)
        assert kill_switch_engaged(store) is False
        assert kill_switch_engaged(store) is False
        assert since == [2, 3]
    finally:
        store.close()


async def _idle_cycle(ctx: Any) -> dict[str, Any]:
    return {"ok": True}


def _idle_supervisor(store: LedgerStore, clock: FixtureClock) -> Supervisor:
    return Supervisor(
        store=store,
        clock=clock,
        rng=make_rng(13),
        cycles=dict.fromkeys(ROSTER, _idle_cycle),
    )


def test_health_body_reports_halt_and_breaker_state(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        supervisor = _idle_supervisor(store, FixtureClock(start=1_000.0))
        healthy = supervisor.health_status()
        assert healthy["ledger_status"] == "CONSISTENT"
        assert healthy["halted"] is False
        store.append(
            ts_utc=format_ts_utc(1_001.0),
            source="replay",
            correlation_id="desk",
            idempotency_key="halt-1",
            type="HaltSet",
            payload={
                "source": "replay",
                "reason": "daily_loss",
                "detail": "test halt",
                "equity_lamports": 1,
                "day_start_equity_lamports": 2,
                "set_by": "risk_engine",
            },
        )
        store.append(
            ts_utc=format_ts_utc(1_002.0),
            source="replay",
            correlation_id="desk",
            idempotency_key="breaker-1",
            type="BreakerTripped",
            payload={
                "source": "replay",
                "breaker": "exec_errors",
                "metric": "rpc_error",
                "threshold": "3",
                "cooldown_s": 60,
            },
        )
        body = supervisor.health_status()
        assert body["halted"] is True
        assert body["breaker"] == "open"
        assert body["breakers"] == {"exec_errors": "open"}
        assert body["status"] == "degraded"
    finally:
        store.close()


def test_unreadable_ledger_falls_back_to_manual_ticket_and_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    store = _store(tmp_path)
    try:
        supervisor = _idle_supervisor(store, FixtureClock(start=1_000.0))

        def _unreadable(**_kwargs: Any) -> list[dict[str, Any]]:
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(store, "read", _unreadable)
        with caplog.at_level(logging.WARNING, logger="pumpgrok.supervisor.scheduler"):
            assert supervisor.autonomy_level() == "manual-ticket"
        assert "autonomy level unreadable" in caplog.text
    finally:
        store.close()


def test_autonomy_fallback_does_not_mask_programming_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(tmp_path)
    try:
        supervisor = _idle_supervisor(store, FixtureClock(start=1_000.0))

        def _broken(**_kwargs: Any) -> list[dict[str, Any]]:
            raise RuntimeError("bug")

        monkeypatch.setattr(store, "read", _broken)
        with pytest.raises(RuntimeError):
            supervisor.autonomy_level()
    finally:
        store.close()


def test_repeated_rollover_failures_latch_the_day_and_report_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FixtureClock(start=1_767_225_600.0)
    store = _store(tmp_path)
    try:
        supervisor = _idle_supervisor(store, clock)
        attempts: list[str] = []

        def _refuse(**_kwargs: Any) -> None:
            attempts.append("append")
            raise OSError("disk full")

        monkeypatch.setattr(store, "append", _refuse)
        for _ in range(5):
            supervisor._emit_rollover(clock.now())
        # Three failed appends latch the day (ROLLOVER_FAILURE_LIMIT); no fourth is attempted.
        assert len(attempts) == 3
        body = supervisor.health_status()
        assert body["rollover_failed"] is True
        assert body["status"] == "degraded"
    finally:
        store.close()
