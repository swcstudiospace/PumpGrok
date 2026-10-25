"""Restored observe-only latches reach the risk engine before the first seat cycle.

A latch restored from the ledger during construction is pushed to the risk engine while the
Supervisor is built, so a sniper buy cannot run ahead of the first tick. A ledger that cannot
be read during construction latches every seat with ``ledger_read_failed``, and a later
successful read does not lift that latch without a human resume.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.supervisor.scheduler import ROSTER, Supervisor
from pumpgrok.supervisor.seat_task import (
    KIND_LEDGER_READ_FAILED,
    KIND_RESTART_EXHAUSTED,
    append_escalation,
)

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
RISK_SEAT = "bot-02-risk"


class _RecordingRisk:
    """Stands in for the RiskEngine: records the observe-only set it is handed."""

    def __init__(self) -> None:
        self.latched: frozenset[str] = frozenset()

    def set_observe_only(self, seats: frozenset[str]) -> None:
        self.latched = frozenset(seats)

    async def poll_kill_sources(self) -> None:
        return None


async def _ok(ctx: Any) -> dict[str, Any]:
    return {"ok": True}


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    return LedgerStore(str(path))


async def test_restored_latch_is_in_the_risk_engine_before_the_first_cycle(
    tmp_path: Path,
) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        append_escalation(
            store,
            clock,
            kind=KIND_RESTART_EXHAUSTED,
            seat=RISK_SEAT,
            detail=f"{RISK_SEAT} restart budget exhausted; observe-only",
            source="paper",
            correlation_id="desk",
        )
        risk = _RecordingRisk()
        seen_at_first_cycle: list[frozenset[str]] = []

        async def _probe(ctx: Any) -> dict[str, Any]:
            if not seen_at_first_cycle:
                seen_at_first_cycle.append(risk.latched)
            return {"ok": True}

        supervisor = Supervisor(
            store=store,
            clock=clock,
            rng=make_rng(7),
            cycles=dict.fromkeys(ROSTER, _probe),
            risk=risk,
        )
        assert supervisor.observe_only.is_latched(RISK_SEAT) is True
        assert RISK_SEAT in risk.latched

        await supervisor.run_once()

        assert len(seen_at_first_cycle) == 1
        assert RISK_SEAT in seen_at_first_cycle[0]
    finally:
        store.close()


async def test_unreadable_ledger_at_construction_latches_every_seat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:

        def _unreadable(**_kwargs: Any) -> list[dict[str, Any]]:
            raise RuntimeError("ledger unreadable")

        monkeypatch.setattr(store, "read", _unreadable)
        risk = _RecordingRisk()
        supervisor = Supervisor(
            store=store,
            clock=clock,
            rng=make_rng(7),
            cycles=dict.fromkeys(ROSTER, _ok),
            risk=risk,
        )

        assert supervisor.observe_only.seats() == frozenset(ROSTER)
        assert supervisor.observe_only.reason(RISK_SEAT) == KIND_LEDGER_READ_FAILED
        assert risk.latched == frozenset(ROSTER)

        # The ledger reads again, but no human resume note was written: the latch holds.
        monkeypatch.undo()
        assert supervisor.observe_only.fold_resume(store) == []
        assert supervisor.observe_only.is_latched(RISK_SEAT) is True
    finally:
        store.close()
