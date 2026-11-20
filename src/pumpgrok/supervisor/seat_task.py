"""Per-seat task wrapper: heartbeats, bounded restarts, observe-only latch.

``SeatTask`` owns one seat's execution record. The wrapper - never the bot -
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
import sqlite3
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pumpgrok.core.errors import CorruptState
from pumpgrok.core.ids import Clock
from pumpgrok.replay.clock import format_ts_utc
from pumpgrok.risk.engine import halt_key
from pumpgrok.supervisor.seat_relay import (
    KIND_HEARTBEAT_STALE,
    KIND_LEDGER_READ_FAILED,
    KIND_RESTART_EXHAUSTED,
    append_escalation,
    escalation_severity,
)
from pumpgrok.supervisor.seat_restart import (
    ObserveOnly,
    RestartPolicy,
    resume_after,
)

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore
    from pumpgrok.tools.notify.notifier import Notifier

__all__ = [
    "STALE_CADENCES",
    "CycleFn",
    "SeatContext",
    "SeatTask",
]

log = logging.getLogger(__name__)

#: A seat is stale after 3 missed cadences (paper-engine.md 6.3).
STALE_CADENCES = 3


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
        stale_cadence_s: float | None = None,
    ) -> None:
        self.seat_id = seat_id
        self.cadence_s = cadence_s
        # The heartbeat grace is the seat's production cadence, independent of how often
        # a fixture timeline polls it (cadence_s); defaults to cadence_s.
        self.stale_cadence_s = stale_cadence_s if stale_cadence_s is not None else cadence_s
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

        self._rebuild_exhaustion_latch()
        self._restore_latched_exit_halt()

    def _restore_latched_exit_halt(self) -> None:
        """Restore EXIT's protective halt when a rebuilt latch demands it (fail closed)."""
        if self.seat_id == "bot-06-exit" and self._observe_only.is_latched(self.seat_id):
            # A latch rebuilt from the ledger must not leave buys open because the original
            # halt write never landed: restore the protective halt before any seat runs.
            try:
                self._append_exit_halt(self._correlation_id)
            except CorruptState as exc:
                # Fail closed (INT-02): without recorded genesis equity there is no
                # safe equity to stamp on the restored halt, so no halt is written
                # and no zero-equity default is substituted. Treat it like an
                # unreadable ledger: stay latched observe-only, escalate with the
                # existing vocabulary, and never propagate out of the constructor.
                log.error("exit halt rebuild failed for %s: %s", self.seat_id, exc)
                self._latch_unreadable_ledger()
                try:
                    append_escalation(
                        self._store,
                        self._clock,
                        kind=KIND_LEDGER_READ_FAILED,
                        seat=self.seat_id,
                        detail=f"{self.seat_id} exit halt not restored: {exc}",
                        source=self._source,
                        correlation_id=self._correlation_id,
                    )
                except Exception as append_exc:
                    log.warning("escalation append failed for %s: %s", self.seat_id, append_exc)

    def _rebuild_exhaustion_latch(self) -> None:
        """Re-latch an exhausted seat from the ledger after a restart.

        The latch lives in memory, so a restarted process would run an exhausted seat again.
        The newest ``bot_restart_exhausted`` escalation for this seat latches it, unless a human
        resume note was appended after that escalation (the same rule ``fold_resume`` applies).
        An unreadable ledger latches the seat with ``ledger_read_failed`` instead: the restored
        state is unknown, so the seat stays observe-only until a human resumes it.
        """
        try:
            escalations = self._store.read(types=["Escalation"], limit=None)
            notes = self._store.read(types=["JournalNote"], limit=None)
        except Exception as exc:
            log.error("exhaustion latch rebuild failed for %s: %s", self.seat_id, exc)
            self._latch_unreadable_ledger()
            return
        newest: Mapping[str, Any] | None = None
        for event in escalations:
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            if payload.get("kind") != KIND_RESTART_EXHAUSTED:
                continue
            if payload.get("seat") == self.seat_id:
                newest = event
        if newest is None:
            return
        floor = int(newest.get("seq", 0))
        if resume_after(notes, self.seat_id, floor):
            return
        self._observe_only.latch(self.seat_id, KIND_RESTART_EXHAUSTED, after_seq=floor)

    def _latch_unreadable_ledger(self) -> None:
        """Latch observe-only with ``ledger_read_failed`` when the ledger cannot be read.

        ``fold_resume`` clears a latch only on a human resume note after its sequence floor,
        which is the ledger head here. When the head is unknown too, ``sys.maxsize`` keeps the
        latch for the life of this process, so no resume note can clear it early.
        """
        try:
            floor = self._store.count()
        except Exception:
            floor = sys.maxsize
        self._observe_only.latch(self.seat_id, KIND_LEDGER_READ_FAILED, after_seq=floor)

    @property
    def timeout_s(self) -> float:
        """Cycle timeout: max(30 s, 4 x cadence) via clock.timeout."""
        return max(30.0, 4.0 * self.cadence_s)

    def is_stale(self, now: float) -> bool:
        """Stale after 3 missed cadences (paper-engine.md 6.3)."""
        if self.last_finished_at is None:
            return False
        return now - self.last_finished_at > STALE_CADENCES * self.stale_cadence_s

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
        if self.seat_id == "bot-06-exit" and self._observe_only.is_latched(self.seat_id):
            # EXIT owes its protective halt until it lands. A restored latch does not crash
            # again, so the crash-path retry alone would never write it (day-keyed, idempotent).
            self._append_exit_halt(ctx.correlation_id)
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
            # Already latched: the escalation and relay fired once on the rising edge and
            # must not repeat. EXIT's halt is retried at the start of every cycle instead.
            return
        # seq is contiguous from 1 (hash chain), so the row count is the head seq.
        self._observe_only.latch(
            self.seat_id, KIND_RESTART_EXHAUSTED, after_seq=self._store.count()
        )
        if self.seat_id == "bot-06-exit":
            # Halt first: a failed escalation write must not leave EXIT unhalted.
            self._append_exit_halt(ctx.correlation_id)
        append_escalation(
            self._store,
            self._clock,
            kind=KIND_RESTART_EXHAUSTED,
            seat=self.seat_id,
            detail=f"{self.seat_id} restart budget exhausted; observe-only",
            source=self._source,
            correlation_id=self._correlation_id,
        )
        await self._relay(KIND_RESTART_EXHAUSTED, f"{self.seat_id} restart budget exhausted")

    def _append_exit_halt(self, correlation_id: str) -> None:
        """Exit seat unmanaged: HaltSet(reason=manual) via the day idempotency."""
        ts_utc = format_ts_utc(self._clock.now())
        equity = self._initial_equity()
        try:
            self._store.append(
                ts_utc=ts_utc,
                source=self._source,
                correlation_id=correlation_id,
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
        except sqlite3.IntegrityError:
            # Day-keyed row already recorded: the retry is a no-op by design.
            log.debug("exit halt already recorded for %s", ts_utc[:10])
        except Exception as exc:
            log.warning("exit halt append failed: %s", exc)

    def _initial_equity(self) -> int:
        """Recorded initial equity; missing or corrupt meta raises, never 0."""
        try:
            meta = self._store.get_meta("initial_equity_lamports")
        except sqlite3.Error as exc:
            raise CorruptState(
                f"seat {self.seat_id}: cannot read initial_equity_lamports: {exc}"
            ) from exc
        if meta is None:
            raise CorruptState(
                f"seat {self.seat_id}: initial_equity_lamports meta is missing; "
                "refusing a zero-equity default"
            )
        try:
            return int(meta)
        except (TypeError, ValueError) as exc:
            raise CorruptState(
                f"seat {self.seat_id}: corrupt initial_equity_lamports {meta!r}; "
                "refusing a zero-equity default"
            ) from exc

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
