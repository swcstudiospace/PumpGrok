"""Per-seat task wrapper: heartbeats, bounded restarts, observe-only latch.

``SeatTask`` owns one seat's execution record. The wrapper — never the bot —
records ``(started_at, finished_at, ok, duration_s)`` so a seat cannot fake
its own heartbeat (paper-engine.md 6.3). A cycle that raises, or that
exceeds ``clock.timeout(max(30, 4 * cadence))``, counts as a crash and feeds
the restart policy; an exhausted budget latches the seat observe-only and
appends one edge-triggered ``Escalation(kind=bot_restart_exhausted)`` while
the other seats keep ticking (paper-engine.md 6.4).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pumpgrok.core.ids import Clock
from pumpgrok.replay.clock import format_ts_utc, parse_ts_utc
from pumpgrok.risk.engine import halt_key

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore
    from pumpgrok.tools.notify.notifier import Notifier

log = logging.getLogger(__name__)

#: Restart budget: 5 restarts per rolling hour (paper-engine.md 6.4).
RESTART_CAPACITY = 5
#: Rolling window for the restart budget (seconds).
RESTART_WINDOW_S = 3600.0
#: Backoff cap (seconds); attempt n waits min(16, 2**n) plus rng jitter.
BACKOFF_CAP_S = 16.0
#: A seat is stale after 3 missed cadences (paper-engine.md 6.3).
STALE_CADENCES = 3
#: Escalation kinds this module appends.
KIND_RESTART_EXHAUSTED = "bot_restart_exhausted"
KIND_HEARTBEAT_STALE = "heartbeat_stale"
#: Resume note prefix written by ``state resume`` (cli.py).
RESUME_PREFIX = "resume "
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


@dataclass
class SeatContext:
    """What one seat cycle may read. Cycles never touch the wall clock."""

    seat_id: str
    clock: Clock
    rng: Any
    store: LedgerStore
    autonomy_level: str = "manual-ticket"
    observe_only: bool = False
    source: str = "paper"
    correlation_id: str = "desk"
    degraded: Any = None


CycleFn = Callable[[SeatContext], Awaitable[Mapping[str, Any] | None]]


@dataclass
class RestartPolicy:
    """Token bucket: 5 restarts per rolling hour with jittered backoff.

    ``record_crash`` prunes crashes older than the window and reports
    whether the seat may restart. ``backoff_s`` is ``min(16, 2**n)`` plus
    ``rng.uniform(0, 1)`` jitter from the seeded rng, where ``n`` is the
    number of crashes already in the window. A clean hour resets the count.
    The seat gates ``not_before`` on the backoff instead of sleeping, so a
    virtual clock never stalls the supervisor loop.
    """

    capacity: int = RESTART_CAPACITY
    window_s: float = RESTART_WINDOW_S
    crashes: list[float] = field(default_factory=list)

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_s
        self.crashes = [ts for ts in self.crashes if ts > cutoff]

    def record_crash(self, now: float) -> bool:
        """Record a crash; True means restart, False means budget exhausted."""
        self._prune(now)
        if len(self.crashes) >= self.capacity:
            return False
        self.crashes.append(now)
        return True

    def attempt(self, now: float) -> int:
        """Crashes in the window (0-based attempt for the next backoff)."""
        self._prune(now)
        return len(self.crashes)

    def backoff_s(self, rng: Any, now: float) -> float:
        """Jittered backoff for the current attempt count."""
        n = max(0, self.attempt(now) - 1)
        return float(min(BACKOFF_CAP_S, 2.0**n) + rng.uniform(0.0, 1.0))


class ObserveOnly:
    """Desk-wide observe-only latch set (paper-engine.md 6.4, RISK-006).

    A latched seat keeps running its cycle but cannot resolve paper-write
    tools: the sniper latch stops buys desk-wide (nobody else can buy),
    the risk latch rejects buys while exits continue, and the exit latch
    appends ``HaltSet(reason=manual)`` because open positions would be
    unmanaged. Cleared by ``state resume --seat --by human:<name>``, which
    the scheduler folds from the ledger every tick.
    """

    def __init__(self) -> None:
        self._latched: dict[str, str] = {}
        self._latched_after: dict[str, int] = {}

    def latch(self, seat: str, reason: str, *, after_seq: int = 0) -> None:
        """Latch a seat observe-only; re-latching keeps the first reason and sequence.

        ``after_seq`` is the ledger head when the latch was set. Only a resume
        note appended after it clears the latch; older notes are history.
        """
        if seat in self._latched:
            return
        self._latched[seat] = reason
        self._latched_after[seat] = after_seq

    def is_latched(self, seat: str) -> bool:
        """Whether the seat is currently observe-only."""
        return seat in self._latched

    def reason(self, seat: str) -> str | None:
        """Latch reason, or None when the seat is live."""
        return self._latched.get(seat)

    def seats(self) -> frozenset[str]:
        """Currently latched seats."""
        return frozenset(self._latched)

    def paper_write_allowed(self, seat: str, side: str) -> bool:
        """RISK-006 matrix: who may still resolve paper-write tools."""
        if seat in self._latched:
            return False
        buys_off = "bot-04-sniper" in self._latched or "bot-02-risk" in self._latched
        return not (side == "buy" and buys_off)

    def fold_resume(self, store: LedgerStore) -> list[str]:
        """Clear latches with a human resume note appended after the latch.

        Returns the resumed seats. Older resume notes are history, never a clear.
        """
        resumed: list[str] = []
        try:
            notes = store.read(types=["JournalNote"], limit=None)
        except Exception as exc:
            log.debug("resume fold skipped: %s", exc)
            return resumed
        for seat in list(self._latched):
            floor = self._latched_after[seat]
            for event in notes:
                if int(event.get("seq", 0)) <= floor:
                    continue
                payload = event.get("payload")
                if not isinstance(payload, dict):
                    continue
                if payload.get("note_kind") != "note":
                    continue
                if str(payload.get("seat", "")) != seat:
                    continue
                text = str(payload.get("text", ""))
                if text.startswith(f"{RESUME_PREFIX}{seat} by human:"):
                    del self._latched[seat]
                    del self._latched_after[seat]
                    resumed.append(seat)
                    break
        return resumed


class SeatTask:
    """Heartbeat and restart wrapper around one seat's cycle callable."""

    def __init__(
        self,
        seat_id: str,
        cadence_s: float,
        cycle: CycleFn,
        *,
        clock: Clock,
        rng: Any,
        store: LedgerStore,
        source: str = "paper",
        correlation_id: str = "desk",
        notifier: Notifier | None = None,
        observe_only: ObserveOnly | None = None,
        policy: RestartPolicy | None = None,
        cycle_observer: Callable[[str, float, str], None] | None = None,
    ) -> None:
        self.seat_id = seat_id
        self.cadence_s = cadence_s
        self._cycle = cycle
        self._clock = clock
        self._rng = rng
        self._store = store
        self._source = source
        self._correlation_id = correlation_id
        self._notifier = notifier
        self._observe_only = observe_only if observe_only is not None else ObserveOnly()
        self._policy = policy if policy is not None else RestartPolicy()
        self._cycle_observer = cycle_observer
        self.last_started_at: float | None = None
        self.last_finished_at: float | None = None
        self.last_ok: bool | None = None
        self.last_duration_s: float = 0.0
        self.cycles: int = 0
        self.crashes: int = 0
        self.restarts = 0
        self.not_before: float | None = None
        self._stale_raised: bool = False

    @property
    def timeout_s(self) -> float:
        """Cycle timeout: max(30 s, 4 x cadence) via clock.timeout."""
        return max(30.0, 4.0 * self.cadence_s)

    def is_stale(self, now: float) -> bool:
        """Stale after 3 missed cadences (paper-engine.md 6.3)."""
        if self.last_finished_at is None:
            return False
        return now - self.last_finished_at > STALE_CADENCES * self.cadence_s

    def is_due(self, now: float) -> bool:
        """Due when the backoff window passed and a full cadence elapsed."""
        if self.not_before is not None and now < self.not_before:
            return False
        if self.last_started_at is None:
            return True
        return now - self.last_started_at >= self.cadence_s

    async def run_guarded(self, ctx: SeatContext) -> str:
        """Run one cycle under the clock timeout; timeout counts as a crash.

        Returns ``"ok"`` or ``"crash"``. ``CancelledError`` (shutdown drain)
        propagates; every other failure feeds the restart policy.
        """
        started = self._clock.now()
        self.last_started_at = started
        outcome = "ok"
        try:
            async with self._clock.timeout(self.timeout_s):
                await self._cycle(ctx)
        except TimeoutError:
            outcome = "crash"
            log.warning("seat %s cycle timed out after %.0fs", self.seat_id, self.timeout_s)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            outcome = "crash"
            log.warning("seat %s cycle crashed: %s", self.seat_id, exc)
        finished = self._clock.now()
        self.last_finished_at = finished
        self.last_duration_s = max(0.0, finished - started)
        self.last_ok = outcome == "ok"
        self._observe_cycle(outcome)
        self.cycles += 1
        if outcome == "ok":
            self._stale_raised = False
        else:
            self.crashes += 1
            await self._on_crash(ctx)
        return outcome

    def _observe_cycle(self, outcome: str) -> None:
        """Report virtual seconds and outcome to the metrics observer, if any.

        Best-effort telemetry: an observer failure must never break the cycle.
        The observer (Metrics.observe) records the histogram at the site that
        sets last_duration_s and counts crashes at the site that increments
        crashes, without seat_task.py importing prometheus_client.
        """
        if self._cycle_observer is None:
            return
        try:
            self._cycle_observer(self.seat_id, self.last_duration_s, outcome)
        except Exception as exc:
            log.warning("seat %s cycle observer failed: %s", self.seat_id, exc)

    async def _on_crash(self, ctx: SeatContext) -> None:
        now = self._clock.now()
        if self._policy.record_crash(now):
            self.restarts += 1
            self.not_before = now + self._policy.backoff_s(self._rng, now)
            return
        if self._observe_only.is_latched(self.seat_id):
            # Already latched: the rising edge escalated and relayed once. A seat
            # that keeps failing must not append a row per cycle.
            return
        # seq is contiguous from 1 (hash chain), so the row count is the head seq.
        self._observe_only.latch(
            self.seat_id, KIND_RESTART_EXHAUSTED, after_seq=self._store.count()
        )
        append_escalation(
            self._store,
            self._clock,
            kind=KIND_RESTART_EXHAUSTED,
            seat=self.seat_id,
            detail=f"{self.seat_id} restart budget exhausted; observe-only",
            source=self._source,
            correlation_id=self._correlation_id,
        )
        if self.seat_id == "bot-06-exit":
            self._append_exit_halt(ctx)
        await self._relay(KIND_RESTART_EXHAUSTED, f"{self.seat_id} restart budget exhausted")

    def _append_exit_halt(self, ctx: SeatContext) -> None:
        """Exit seat unmanaged: HaltSet(reason=manual) via the day idempotency."""
        ts_utc = format_ts_utc(self._clock.now())
        equity = self._initial_equity()
        try:
            self._store.append(
                ts_utc=ts_utc,
                source=self._source,
                correlation_id=ctx.correlation_id,
                idempotency_key=halt_key("manual", ts_utc[:10]),
                type="HaltSet",
                payload={
                    "source": self._source,
                    "reason": "manual",
                    "detail": "exit seat observe-only",
                    "equity_lamports": equity,
                    "day_start_equity_lamports": equity,
                    "set_by": "risk_engine",
                },
            )
        except Exception as exc:
            log.warning("exit halt append failed: %s", exc)

    def _initial_equity(self) -> int:
        try:
            meta = self._store.get_meta("initial_equity_lamports")
            return int(meta) if meta is not None else 0
        except Exception:
            return 0

    async def check_stale(self, now: float) -> bool:
        """Edge-triggered heartbeat_stale escalation; True on the rising edge."""
        if not self.is_stale(now) or self._stale_raised:
            return False
        self._stale_raised = True
        append_escalation(
            self._store,
            self._clock,
            kind=KIND_HEARTBEAT_STALE,
            seat=self.seat_id,
            detail=f"{self.seat_id} stale for 3 cadences",
            source=self._source,
            correlation_id=self._correlation_id,
        )
        await self._relay(KIND_HEARTBEAT_STALE, f"{self.seat_id} heartbeat stale")
        return True

    async def _relay(self, kind: str, text: str) -> None:
        if self._notifier is None:
            return
        try:
            await self._notifier.send(
                severity=escalation_severity(kind),
                kind=kind,
                text=text,
                fields={"seat": self.seat_id},
                idempotency_key=f"escalation|{kind}|{self.seat_id}|{self._clock.now():.0f}",
            )
        except Exception as exc:
            log.warning("escalation relay failed for %s: %s", self.seat_id, exc)


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
