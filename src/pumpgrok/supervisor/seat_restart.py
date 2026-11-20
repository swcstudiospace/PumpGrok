"""Restart budget, jittered backoff and the desk-wide observe-only latch.

``RestartPolicy`` bounds one seat's crash restarts; ``ObserveOnly`` latches a seat
observe-only once its budget is spent, until a human resume note clears it.
Split out of ``seat_task.py`` by plan 11-09; behaviour is unchanged and pinned by
``tests/supervisor/test_seat_task_characterization.py``.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore

log = logging.getLogger(__name__)

#: Restart budget: 5 restarts per rolling hour (paper-engine.md 6.4).
RESTART_CAPACITY = 5
#: Rolling window for the restart budget (seconds).
RESTART_WINDOW_S = 3600.0
#: Backoff cap (seconds); attempt n waits min(16, 2**n) plus rng jitter.
BACKOFF_CAP_S = 16.0
#: Resume note prefix written by ``state resume`` (cli.py).
RESUME_PREFIX = "resume "


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


def resume_after(notes: Sequence[Mapping[str, Any]], seat: str, floor: int) -> bool:
    """True when a human resume note for ``seat`` was appended after ledger sequence ``floor``."""
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
        if str(payload.get("text", "")).startswith(f"{RESUME_PREFIX}{seat} by human:"):
            return True
    return False


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
            if resume_after(notes, seat, self._latched_after[seat]):
                del self._latched[seat]
                del self._latched_after[seat]
                resumed.append(seat)
        return resumed
