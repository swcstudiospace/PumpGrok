"""The ledger-tail relay never moves its cursor past an alert whose send failed.

A failed send stays behind the cursor, so the next pass retries it. Offline: a temp ledger and a
scripted notifier that fails only the alert whose detail carries the marker.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.seat_task import append_escalation, relay_tail

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
KIND = "restart_exhausted"


class _ScriptedNotifier:
    """Records every send attempt; raises for texts carrying a ``fail_on`` marker."""

    def __init__(self, fail_on: tuple[str, ...] = ()) -> None:
        self.fail_on = fail_on
        self.attempted: list[str] = []
        self.delivered: list[str] = []

    async def send(self, **kwargs: Any) -> None:
        text = str(kwargs["text"])
        self.attempted.append(text)
        if any(marker in text for marker in self.fail_on):
            raise RuntimeError("transport down")
        self.delivered.append(text)


@pytest.fixture
def ledger(tmp_path: Path) -> Iterator[LedgerStore]:
    store = LedgerStore(str(tmp_path / "replay.sqlite"))
    try:
        yield store
    finally:
        store.close()


def _append_three(store: LedgerStore, clock: FixtureClock) -> tuple[int, int, int]:
    """Escalations ok, critical-FAIL, ok. Returns their seqs in that order."""
    seqs: list[int] = []
    rows = (("bot-01", "first-ok"), ("bot-02", "critical-FAIL"), ("bot-03", "last-ok"))
    for seat, detail in rows:
        row = append_escalation(
            store,
            clock,
            kind=KIND,
            seat=seat,
            detail=detail,
            source="replay",
            correlation_id="relay-test",
        )
        seqs.append(int(row["seq"]))
        clock.advance_to(clock.now() + 1.0)
    return seqs[0], seqs[1], seqs[2]


async def test_failed_send_stops_pass_and_cursor_sits_before_it(ledger: LedgerStore) -> None:
    clock = FixtureClock(start=START)
    first, _failed, _last = _append_three(ledger, clock)
    notifier = _ScriptedNotifier(fail_on=("critical-FAIL",))

    cursor = await relay_tail(ledger, notifier, clock, 0)

    assert cursor == first
    assert notifier.attempted[-1].endswith("critical-FAIL")
    assert not any("last-ok" in text for text in notifier.attempted)


async def test_failed_alert_is_retried_not_skipped_on_next_pass(ledger: LedgerStore) -> None:
    clock = FixtureClock(start=START)
    _first, _failed, last = _append_three(ledger, clock)
    cursor = await relay_tail(ledger, _ScriptedNotifier(fail_on=("critical-FAIL",)), clock, 0)

    recovered = _ScriptedNotifier()
    cursor = await relay_tail(ledger, recovered, clock, cursor)

    assert any(text.endswith("critical-FAIL") for text in recovered.delivered)
    assert any(text.endswith("last-ok") for text in recovered.delivered)
    assert cursor == last


async def test_all_sends_succeeding_advances_cursor_to_end(ledger: LedgerStore) -> None:
    clock = FixtureClock(start=START)
    _first, _failed, last = _append_three(ledger, clock)
    notifier = _ScriptedNotifier()

    cursor = await relay_tail(ledger, notifier, clock, 0)

    assert cursor == last
    assert len(notifier.delivered) == 3
