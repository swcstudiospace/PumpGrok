"""Escalation rows and notify relay for supervisor seats.

``append_escalation`` writes one ``Escalation`` row and refuses the append when
the clock trails the ledger head beyond the skew budget. ``relay_tail`` forwards
new escalation, halt, kill-switch, breaker and live-attempt rows to
``notify.alert``. Split out of ``seat_task.py`` by plan 11-09; behaviour is
unchanged and pinned by ``tests/supervisor/test_seat_task_characterization.py``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pumpgrok.core.ids import Clock
from pumpgrok.replay.clock import format_ts_utc, parse_ts_utc

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore
    from pumpgrok.tools.notify.notifier import Notifier

log = logging.getLogger(__name__)

#: Escalation kinds this module appends.
KIND_RESTART_EXHAUSTED = "bot_restart_exhausted"
KIND_HEARTBEAT_STALE = "heartbeat_stale"
#: Latch reason when the ledger cannot be read at construction (fail closed).
KIND_LEDGER_READ_FAILED = "ledger_read_failed"
#: Clock skew budget: refuse appends when the clock trails the head by more.
CLOCK_SKEW_S = 5.0


class ClockSkew(Exception):
    """Refused append: the clock trails the ledger head beyond the budget."""


#: Relay severity per escalation kind (critical wakes the operator).
_ESCALATION_SEVERITY = {
    KIND_RESTART_EXHAUSTED: "critical",
    KIND_HEARTBEAT_STALE: "warning",
    "persistence_down": "critical",
    "clock_skew": "critical",
    "ledger_inconsistent": "critical",
}

#: Ledger tail event types relayed to notify.alert (paper-engine.md 6.4).
RELAY_TYPES = frozenset(
    {"Escalation", "HaltSet", "KillSwitchSet", "BreakerTripped", "LiveWriteAttempted"}
)

#: notify.alert kind per relayed ledger type.
_RELAY_KIND = {
    "Escalation": "escalation",
    "HaltSet": "halt",
    "KillSwitchSet": "killswitch",
    "BreakerTripped": "breaker",
    "LiveWriteAttempted": "escalation",
}


def escalation_severity(kind: str) -> str:
    """Alert severity for an escalation kind; unknown kinds warn."""
    return _ESCALATION_SEVERITY.get(kind, "warning")


def append_escalation(
    store: LedgerStore,
    clock: Clock,
    *,
    kind: str,
    seat: str,
    detail: str,
    source: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Append one ``Escalation`` row; the idempotency key dedupes replays.

    Refuses when the clock trails the ledger head beyond the 5 s skew
    budget (paper-engine.md 6.7): the skew row itself is appended inline
    and ``ClockSkew`` is raised so no observation lands out of order.
    """
    try:
        head = store.read(limit=None)
        if head:
            head_ts = parse_ts_utc(str(head[-1].get("ts_utc", "")))
            if clock.now() < head_ts - CLOCK_SKEW_S:
                skew_ts = format_ts_utc(clock.now())
                store.append(
                    ts_utc=skew_ts,
                    source=source,
                    correlation_id=correlation_id,
                    idempotency_key=f"escalation|clock_skew|{seat}|{skew_ts}",
                    type="Escalation",
                    payload={
                        "source": source,
                        "kind": "clock_skew",
                        "seat": seat,
                        "detail": "clock trails ledger head; appends refused",
                    },
                )
                raise ClockSkew("clock trails ledger head beyond 5s; append refused")
    except ClockSkew:
        raise
    except Exception as exc:
        log.debug("skew precheck skipped: %s", exc)
    ts_utc = clock.utc_iso() if hasattr(clock, "utc_iso") else ""
    if not ts_utc:
        ts_utc = format_ts_utc(clock.now())
    return store.append(
        ts_utc=ts_utc,
        source=source,
        correlation_id=correlation_id,
        idempotency_key=f"escalation|{kind}|{seat}|{ts_utc}",
        type="Escalation",
        payload={"source": source, "kind": kind, "seat": seat, "detail": detail},
    )


async def relay_tail(
    store: LedgerStore,
    notifier: Notifier | None,
    clock: Clock,
    cursor_seq: int,
) -> int:
    """Relay new Escalation/HaltSet/KillSwitchSet/BreakerTripped rows.

    Returns the new high-water seq. A None notifier only advances the
    cursor; relay failures never raise.
    """
    try:
        events = store.read(since_seq=cursor_seq + 1, limit=None)
    except Exception as exc:
        log.debug("tail relay skipped: %s", exc)
        return cursor_seq
    high = cursor_seq
    for event in events:
        high = max(high, int(event.get("seq", high)))
        event_type = str(event.get("type", ""))
        if event_type not in RELAY_TYPES or notifier is None:
            continue
        payload = event.get("payload")
        detail = payload.get("detail", "") if isinstance(payload, dict) else ""
        kind = _RELAY_KIND.get(event_type, "escalation")
        if event_type == "Escalation" and isinstance(payload, dict):
            kind = str(payload.get("kind", "escalation"))
        try:
            await notifier.send(
                severity="critical" if event_type != "Escalation" else escalation_severity(kind),
                kind=kind,
                text=f"{event_type}: {detail}",
                fields={"seq": event.get("seq")},
                idempotency_key=f"relay|{event_type}|{event.get('seq')}",
            )
        except Exception as exc:
            log.warning("tail relay failed at seq %s: %s", event.get("seq"), exc)
    return high
