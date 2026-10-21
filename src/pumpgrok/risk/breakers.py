"""Risk breakers: vendor CircuitBreaker port plus three domain breakers.

``Breaker`` is a faithful port of ``vendor/grokbot-pumpfun/src/ops.py:131-182``
with two additions from paper-engine.md 5.3: an explicit ``half_open`` state
that admits exactly one probe, and hysteresis (``reset_after_ok``
consecutive successes before ``closed``). The characterization suite
(``tests/characterization/test_vendor_ops.py``) runs against this port.

Domain breakers (thresholds and cooldowns are REVIEW defaults):

- ``DataStaleBreaker``: 120 s silent or 3 consecutive misses; 60 s cooldown;
  3 consecutive fresh ticks within 30 s to reset.
- ``LossVelocityBreaker``: 2 percent equity drop over a rolling 15 min
  window; 30 min cooldown; reset when the 5 min window loss drops below
  0.5 percent.
- ``ExecErrorsBreaker``: 3 qualifying rejects within 10 min; 15 min cooldown;
  reset by one filled probe order.

``BreakerSet`` owns the three breakers plus ledger persistence. Only
``RiskEngine`` drives it, so only ``RiskEngine`` appends ``BreakerTripped``
and ``BreakerReset`` rows (R24). State rebuilds from ledger events on
restart, so a restart cannot bypass a cooldown.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections import deque
from collections.abc import Callable

from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import Clock, parse_ts_utc

EXEC_ERROR_REASONS: frozenset[str] = frozenset(
    {"tx_dropped", "slippage_exceeded", "quote_unavailable", "rpc_error"}
)

BREAKER_NAMES: tuple[str, ...] = ("data_stale", "loss_velocity", "exec_errors")

THRESHOLDS: dict[str, str] = {
    "data_stale": "120s-silence-or-3-misses",
    "loss_velocity": "2pct-over-15min",
    "exec_errors": "3-rejects-in-10min",
}

#: DataStale defaults (paper-engine.md 5.3 REVIEW values).
DATA_STALE_S = 120.0
DATA_STALE_MISSES = 3
DATA_STALE_COOLDOWN_S = 60.0
DATA_STALE_RESET_OK = 3
DATA_STALE_FRESH_WINDOW_S = 30.0

#: LossVelocity defaults: 2 percent drop over rolling 15 min, 30 min
#: cooldown, reset when the 5 min window loss drops below 0.5 percent.
LOSS_VELOCITY_FRACTION = 0.02
LOSS_VELOCITY_WINDOW_S = 900.0
LOSS_VELOCITY_COOLDOWN_S = 1800.0
LOSS_VELOCITY_RESET_WINDOW_S = 300.0
LOSS_VELOCITY_RESET_FRACTION = 0.005

#: ExecErrors defaults: 3 qualifying rejects within 10 min, 15 min cooldown.
EXEC_ERRORS_REJECTS = 3
EXEC_ERRORS_WINDOW_S = 600.0
EXEC_ERRORS_COOLDOWN_S = 900.0


def breaker_trip_key(breaker: str, day_utc: str) -> str:
    """Idempotency per (breaker, utc_day): one trip per breaker per day (R24)."""
    return hashlib.sha256(f"BreakerTripped|{breaker}|{day_utc}".encode()).hexdigest()


def breaker_reset_key(breaker: str, day_utc: str) -> str:
    """Idempotency per (breaker, utc_day) for resets."""
    return hashlib.sha256(f"BreakerReset|{breaker}|{day_utc}".encode()).hexdigest()


class Breaker:
    """Consecutive-failure breaker with cooldown, half-open probe and hysteresis.

    Closed until ``threshold`` consecutive failures trip it. After
    ``cooldown_s`` it goes half-open and admits exactly one probe via
    :meth:`admit_probe`; the probe outcome returns through
    :meth:`resolve_probe`. ``reset_after_ok`` consecutive successes close it.
    """

    def __init__(
        self,
        failures: int,
        cooldown_s: float,
        now: Callable[[], float],
        reset_after_ok: int = 1,
    ) -> None:
        self.threshold = max(1, failures)
        self.cooldown_s = max(0.0, cooldown_s)
        self._now = now
        self.reset_after_ok = max(1, reset_after_ok)
        self.consecutive_failures = 0
        self.successes = 0
        self.opened_at: float | None = None
        self.half_open = False
        self.probe_inflight = False
        self.trips = 0

    @property
    def is_open(self) -> bool:
        """Open and within cooldown; expiry transitions to half-open."""
        if self.opened_at is None:
            return False
        if self._now() - self.opened_at >= self.cooldown_s:
            self.opened_at = None
            self.half_open = True
            self.consecutive_failures = self.threshold - 1
            self.successes = 0
            return False
        return True

    @property
    def state(self) -> str:
        """``open``, ``half-open`` or ``closed`` (vendor mirror vocabulary)."""
        if self.is_open:
            return "open"
        return "half-open" if self.consecutive_failures else "closed"

    def remaining_cooldown(self) -> float:
        """Seconds until half-open; zero when closed or already half-open."""
        if self.opened_at is None:
            return 0.0
        return max(0.0, self.cooldown_s - (self._now() - self.opened_at))

    def trip(self, at: float | None = None) -> None:
        """Force open now (domain trip conditions call this)."""
        self.opened_at = at if at is not None else self._now()
        self.trips += 1
        self.half_open = False
        self.consecutive_failures = self.threshold
        self.successes = 0

    def record_success(self) -> None:
        """One success; ``reset_after_ok`` consecutive successes close."""
        self.successes += 1
        if self.successes >= self.reset_after_ok:
            self.consecutive_failures = 0
            self.successes = 0
            self.opened_at = None
            self.half_open = False

    def record_failure(self) -> None:
        """One failure; ``threshold`` consecutive failures trip."""
        self.consecutive_failures += 1
        self.successes = 0
        if self.consecutive_failures >= self.threshold and self.opened_at is None:
            self.trip()

    def admit_probe(self) -> bool:
        """Admit the single half-open probe; False when closed, open or taken."""
        if self.is_open:
            return False
        if not self.half_open or self.probe_inflight:
            return False
        self.probe_inflight = True
        return True

    def resolve_probe(self, ok: bool) -> None:
        """Close the admitted probe: success counts, failure re-opens."""
        if not self.probe_inflight:
            raise ValueError("no probe inflight to resolve")
        self.probe_inflight = False
        if ok:
            self.record_success()
        else:
            self.consecutive_failures = self.threshold
            self.successes = 0
            self.opened_at = self._now()
            self.trips += 1


class DataStaleBreaker(Breaker):
    """Trips when the price feed goes silent (120 s or 3 consecutive misses)."""

    def __init__(
        self,
        now: Callable[[], float],
        *,
        data_stale_s: float = DATA_STALE_S,
        max_misses: int = DATA_STALE_MISSES,
        cooldown_s: float = DATA_STALE_COOLDOWN_S,
        reset_after_ok: int = DATA_STALE_RESET_OK,
        fresh_window_s: float = DATA_STALE_FRESH_WINDOW_S,
    ) -> None:
        super().__init__(max_misses, cooldown_s, now, reset_after_ok)
        self.data_stale_s = data_stale_s
        self.max_misses = max_misses
        self.fresh_window_s = fresh_window_s
        self.last_tick: float | None = None
        self.consecutive_misses = 0
        self._prev_tick: float | None = None

    def note_tick(self, ts: float) -> None:
        """A fresh price arrived; a gap restarts the reset streak."""
        if self._prev_tick is not None and ts - self._prev_tick > self.fresh_window_s:
            self.successes = 0
        self._prev_tick = ts
        self.last_tick = ts
        self.consecutive_misses = 0
        self.record_success()

    def note_miss(self, ts: float) -> None:
        """A price read failed; ``max_misses`` consecutive misses trip.

        The trip anchors at the live clock: expiry is measured against it,
        so anchoring a fresh trip at a stale event time would skip ``open``
        and admit a probe immediately.
        """
        self.consecutive_misses += 1
        if self.consecutive_misses >= self.max_misses and not self.is_open:
            self.trip()

    def evaluate(self, now: float) -> str:
        """Trip on silence; never trips before the first tick is observed."""
        if self.is_open or self.half_open:
            return self.state
        if self.last_tick is not None and now - self.last_tick >= self.data_stale_s:
            self.trip()
        return self.state


class LossVelocityBreaker(Breaker):
    """Trips on a 2 percent equity drop over a rolling 15 min window."""

    def __init__(
        self,
        now: Callable[[], float],
        *,
        loss_fraction: float = LOSS_VELOCITY_FRACTION,
        window_s: float = LOSS_VELOCITY_WINDOW_S,
        cooldown_s: float = LOSS_VELOCITY_COOLDOWN_S,
        reset_window_s: float = LOSS_VELOCITY_RESET_WINDOW_S,
        reset_loss_fraction: float = LOSS_VELOCITY_RESET_FRACTION,
    ) -> None:
        super().__init__(1, cooldown_s, now, 1)
        self.loss_fraction = loss_fraction
        self.window_s = window_s
        self.reset_window_s = reset_window_s
        self.reset_loss_fraction = reset_loss_fraction
        self._points: deque[tuple[float, int]] = deque()

    def clear_window(self) -> None:
        """Drop buffered equity points (refresh rebuilds them from the ledger)."""
        self._points.clear()

    def note_equity(self, ts: float, equity_lamports: int) -> None:
        """Record an MTM equity point; history older than both windows is pruned."""
        self._points.append((ts, equity_lamports))
        horizon = max(self.window_s, self.reset_window_s)
        while len(self._points) > 1 and self._points[0][0] < ts - horizon:
            self._points.popleft()

    def _window_loss(self, now: float, window_s: float) -> float | None:
        """(oldest - latest) / oldest over the window; None without history."""
        in_window = [(ts, eq) for ts, eq in self._points if ts >= now - window_s]
        if len(in_window) < 2:
            return None
        old = in_window[0][1]
        new = in_window[-1][1]
        if old <= 0:
            return None
        return (old - new) / old

    def evaluate(self, now: float) -> str:
        """Trip on a fast drop; reset when the short window calms down."""
        if self.is_open or self.half_open:
            reset_loss = self._window_loss(now, self.reset_window_s)
            if reset_loss is not None and reset_loss < self.reset_loss_fraction:
                self.record_success()
            return self.state
        loss = self._window_loss(now, self.window_s)
        if loss is not None and loss >= self.loss_fraction:
            self.trip(now)
        return self.state


class ExecErrorsBreaker(Breaker):
    """Trips on 3 qualifying rejects within 10 min; one filled probe resets."""

    def __init__(
        self,
        now: Callable[[], float],
        max_rejects: int = EXEC_ERRORS_REJECTS,
        window_s: float = EXEC_ERRORS_WINDOW_S,
        cooldown_s: float = EXEC_ERRORS_COOLDOWN_S,
    ) -> None:
        super().__init__(max_rejects, cooldown_s, now, 1)
        self.max_rejects = max_rejects
        self.window_s = window_s
        self._rejects: deque[float] = deque()

    def clear_window(self) -> None:
        """Drop buffered reject times (refresh rebuilds them from the ledger)."""
        self._rejects.clear()

    def note_reject(self, ts: float, reason: str) -> None:
        """Count a qualifying rejection; trip at ``max_rejects`` in-window."""
        if reason not in EXEC_ERROR_REASONS:
            return
        self._rejects.append(ts)
        while self._rejects and self._rejects[0] < ts - self.window_s:
            self._rejects.popleft()
        if len(self._rejects) >= self.max_rejects and not self.is_open:
            self.trip(ts)


class _SuppressIntegrity:
    """A duplicate trip/reset key means another path recorded it already."""

    def __enter__(self) -> _SuppressIntegrity:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return isinstance(exc, sqlite3.IntegrityError)


class BreakerSet:
    """The three domain breakers plus their ledger persistence.

    Constructed and driven by ``RiskEngine`` only. ``refresh`` feeds ledger
    observations and appends trip rows; ``open_breakers`` reports the current
    open set after cooldown expiry; probes flow through ``admit_probe`` and
    ``resolve_probe``.
    """

    def __init__(self, store: LedgerStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock
        now: Callable[[], float] = clock.now
        self.data_stale = DataStaleBreaker(now)
        self.loss_velocity = LossVelocityBreaker(now)
        self.exec_errors = ExecErrorsBreaker(now)

    def by_name(self, name: str) -> Breaker:
        """Return the breaker for ``data_stale``, ``loss_velocity`` or ``exec_errors``."""
        if name == "data_stale":
            return self.data_stale
        if name == "loss_velocity":
            return self.loss_velocity
        if name == "exec_errors":
            return self.exec_errors
        raise KeyError(f"unknown breaker: {name}")

    def note_tick(self, ts: float, *, ts_utc: str, source: str, correlation_id: str) -> None:
        """Record a fresh price and persist any open-to-closed transition."""
        before = self.data_stale.state
        self.data_stale.note_tick(ts)
        self._transition("data_stale", before, ts_utc, source, correlation_id)

    def sync_from_ledger(self) -> None:
        """Adopt ledger-recorded openness the objects have not seen (restart path).

        Live observation buffers (ticks, misses) are preserved; only the
        open/half-open lifecycle aligns with tripped-without-reset rows.
        """
        open_since: dict[str, float] = {}
        for event in self._store.read(limit=None):
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            name = str(payload.get("breaker", ""))
            if name not in BREAKER_NAMES:
                continue
            if event["type"] == "BreakerTripped":
                try:
                    open_since[name] = parse_ts_utc(str(event.get("ts_utc", "")))
                except ValueError:
                    continue
            elif event["type"] == "BreakerReset":
                open_since.pop(name, None)
        for name, since in open_since.items():
            breaker = self.by_name(name)
            if breaker.is_open or breaker.half_open or breaker.probe_inflight:
                continue
            breaker.opened_at = since
            breaker.trips += 1
            breaker.consecutive_failures = breaker.threshold

    def note_miss(self, ts: float, *, ts_utc: str, source: str, correlation_id: str) -> None:
        before = self.data_stale.state
        self.data_stale.note_miss(ts)
        self._transition("data_stale", before, ts_utc, source, correlation_id)

    def refresh(self, *, ts_utc: str, source: str, correlation_id: str, equity_now: int) -> None:
        """Feed ledger observations and persist fresh transition rows (idempotent).

        Windowed buffers rebuild from scratch on every call so repeated
        refreshes never double-count the same ledger rows.
        """
        now = self._clock.now()
        before = {name: self.by_name(name).state for name in BREAKER_NAMES}
        self.exec_errors.clear_window()
        self.loss_velocity.clear_window()
        for event in self._store.read(limit=None):
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            try:
                ts = parse_ts_utc(str(event.get("ts_utc", "")))
            except ValueError:
                continue
            if event["type"] == "OrderRejected":
                if now - ts <= EXEC_ERRORS_WINDOW_S:
                    self.exec_errors.note_reject(ts, str(payload.get("reason", "")))
            elif event["type"] == "MarkToMarket":
                equity = int(payload.get("equity_lamports", 0))
                if equity > 0:
                    self.loss_velocity.note_equity(ts, equity)
        self.loss_velocity.note_equity(now, equity_now)
        for name in BREAKER_NAMES:
            if name == "data_stale":
                self.data_stale.evaluate(now)
            elif name == "loss_velocity":
                self.loss_velocity.evaluate(now)
            self._transition(name, before[name], ts_utc, source, correlation_id)

    def open_breakers(self) -> list[str]:
        """Names currently open (cooldown expiry transitions to half-open)."""
        return [name for name in BREAKER_NAMES if self.by_name(name).is_open]

    def half_open_breakers(self) -> list[str]:
        """Names half-open after cooldown with no probe inflight."""
        self.open_breakers()
        return [
            name
            for name in BREAKER_NAMES
            if self.by_name(name).half_open and not self.by_name(name).probe_inflight
        ]

    def admit_probe(self, name: str) -> bool:
        """Admit the single half-open probe for one breaker."""
        return self.by_name(name).admit_probe()

    def resolve_probe(
        self, name: str, ok: bool, *, ts_utc: str, source: str, correlation_id: str
    ) -> None:
        """Resolve an admitted probe and persist the close on success."""
        breaker = self.by_name(name)
        before = breaker.state
        breaker.resolve_probe(ok)
        self._transition(name, before, ts_utc, source, correlation_id, probe_ok=ok)

    def _transition(
        self,
        name: str,
        before: str,
        ts_utc: str,
        source: str,
        correlation_id: str,
        *,
        probe_ok: bool = False,
    ) -> None:
        after = self.by_name(name).state
        if after == before:
            return
        if after == "open":
            self._append_trip(name, ts_utc, source, correlation_id)
        elif after == "closed":
            self._append_reset(name, ts_utc, source, correlation_id, probe_ok)

    @classmethod
    def rebuild(cls, store: LedgerStore, clock: Clock) -> BreakerSet:
        """Rebuild openness from ledger events (restart cannot bypass cooldown)."""
        made = cls(store, clock)
        open_since: dict[str, float] = {}
        trips: dict[str, int] = {}
        for event in store.read(limit=None):
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            name = str(payload.get("breaker", ""))
            if name not in BREAKER_NAMES:
                continue
            if event["type"] == "BreakerTripped":
                try:
                    open_since[name] = parse_ts_utc(str(event.get("ts_utc", "")))
                except ValueError:
                    continue
                trips[name] = trips.get(name, 0) + 1
            elif event["type"] == "BreakerReset":
                open_since.pop(name, None)
        for name, since in open_since.items():
            breaker = made.by_name(name)
            breaker.opened_at = since
            breaker.trips = trips.get(name, 1)
            breaker.consecutive_failures = breaker.threshold
        return made

    def _append_trip(self, name: str, ts_utc: str, source: str, correlation_id: str) -> None:
        breaker = self.by_name(name)
        with _SuppressIntegrity():
            self._store.append(
                ts_utc=ts_utc,
                source=source,
                correlation_id=correlation_id,
                idempotency_key=breaker_trip_key(name, ts_utc[:10]),
                type="BreakerTripped",
                payload={
                    "source": source,
                    "breaker": name,
                    "metric": name,
                    "threshold": THRESHOLDS[name],
                    "cooldown_s": int(breaker.cooldown_s),
                },
            )

    def _append_reset(
        self,
        name: str,
        ts_utc: str,
        source: str,
        correlation_id: str,
        probe_ok: bool,
    ) -> None:
        with _SuppressIntegrity():
            self._store.append(
                ts_utc=ts_utc,
                source=source,
                correlation_id=correlation_id,
                idempotency_key=breaker_reset_key(name, ts_utc[:10]),
                type="BreakerReset",
                payload={
                    "source": source,
                    "breaker": name,
                    "after_s": 0,
                    "probe_ok": probe_ok,
                },
            )
