"""Regression (R-26): the tail relay holds its mark on a failed send and retries it.

``Notifier.send`` reports a failed sink as an ``ok: false`` row and does not raise, so
both failure signals are covered: a raised exception and a sink reported as failed in
the returned result. Virtual time only (FixtureClock); no wall clock, no sleep.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.supervisor.seat_relay import relay_tail

BASE = 1_000_000.0
EQUITY = 10_000_000_000

_DELIVERED: dict[str, Any] = {
    "delivered": [{"sink": "telegram", "ok": True, "error": None}],
    "suppressed": False,
}
_SINK_DOWN: dict[str, Any] = {
    "delivered": [{"sink": "telegram", "ok": False, "error": "HTTP 503"}],
    "suppressed": False,
}


class _Scripted:
    """Notifier double: each call consumes the next scripted outcome, then delivers.

    An outcome is an exception to raise or the dict ``Notifier.send`` would return.
    """

    def __init__(self, *outcomes: BaseException | dict[str, Any]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    async def send(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        outcome = self._outcomes.pop(0) if self._outcomes else _DELIVERED
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def keys(self) -> list[str]:
        return [str(call["idempotency_key"]) for call in self.calls]


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    return store


def _append_halt(store: LedgerStore, clock: FixtureClock, key: str) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="desk",
        idempotency_key=key,
        type="HaltSet",
        payload={
            "source": "paper",
            "reason": "manual",
            "detail": key,
            "equity_lamports": EQUITY,
            "day_start_equity_lamports": EQUITY,
            "set_by": "risk_engine",
        },
    )


def _append_journal_note(store: LedgerStore, clock: FixtureClock, key: str) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="desk",
        idempotency_key=key,
        type="JournalNote",
        payload={"source": "paper", "seat": "desk", "note_kind": "note", "text": key, "refs": []},
    )


async def test_raised_send_holds_the_mark_and_retries_on_the_next_pass(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        _append_halt(store, clock, "h1")
        notifier = _Scripted(RuntimeError("notify.alert is down"))
        assert await relay_tail(store, notifier, clock, 0) == 0
        assert await relay_tail(store, notifier, clock, 0) == 1
        assert notifier.keys() == ["relay|HaltSet|1", "relay|HaltSet|1"]
    finally:
        store.close()


async def test_sink_reported_failure_holds_the_mark_and_retries(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        _append_halt(store, clock, "h1")
        notifier = _Scripted(_SINK_DOWN)
        assert await relay_tail(store, notifier, clock, 0) == 0
        assert await relay_tail(store, notifier, clock, 0) == 1
        assert notifier.keys() == ["relay|HaltSet|1", "relay|HaltSet|1"]
    finally:
        store.close()


async def test_failed_row_stops_the_pass_so_later_rows_are_not_skipped(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        _append_halt(store, clock, "h1")
        _append_halt(store, clock, "h2")
        notifier = _Scripted(RuntimeError("notify.alert is down"))
        assert await relay_tail(store, notifier, clock, 0) == 0
        assert notifier.keys() == ["relay|HaltSet|1"]
        assert await relay_tail(store, notifier, clock, 0) == 2
        assert notifier.keys() == ["relay|HaltSet|1", "relay|HaltSet|1", "relay|HaltSet|2"]
    finally:
        store.close()


async def test_rows_before_a_failure_advance_the_mark(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        _append_journal_note(store, clock, "n1")
        _append_halt(store, clock, "h2")
        notifier = _Scripted(RuntimeError("notify.alert is down"))
        assert await relay_tail(store, notifier, clock, 0) == 1
        assert await relay_tail(store, notifier, clock, 1) == 2
        assert notifier.keys() == ["relay|HaltSet|2", "relay|HaltSet|2"]
    finally:
        store.close()
