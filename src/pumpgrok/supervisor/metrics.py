"""Supervisor-owned Prometheus registry with the nine OBS-003 families (05-01).

Only the supervisor writes metrics; ``core/`` and ``risk/`` never import
``prometheus_client`` (``tests/safety/test_static_guards.py`` enforces it).
``build_registry()`` returns a fresh :class:`CollectorRegistry` per call --
never the global default -- so tests never collide on duplicate registration.

Nine families, names verbatim (ROADMAP SC2 counts these in source text):

- ``pumpgrok_cycle_seconds{seat}`` histogram (virtual seconds observed from
  ``SeatTask.last_duration_s`` in ``run_guarded``)
- ``pumpgrok_bot_crashes_total{seat}`` counter
- ``pumpgrok_orders_total{side,outcome}`` counter (filled|rejected|unknown_result)
- ``pumpgrok_equity_sol`` gauge (lamports/1e9 computed at scrape only, R28)
- ``pumpgrok_drawdown_pct`` gauge
- ``pumpgrok_data_age_seconds{source}`` gauge
- ``pumpgrok_breaker_state{breaker}`` gauge (0 closed, 1 half-open, 2 open)
- ``pumpgrok_kill_switch`` gauge (0/1)
- ``pumpgrok_ledger_seq`` gauge

Counters are declared with the ``_total`` suffix. Gauges that are state
snapshots are computed at scrape time from a snapshot callable injected by
the supervisor (same callable-injection shape as ``HealthServer``
``get_status``); the counters are event-driven.

Decision record (orders_total source): at scrape time the supervisor
reconciles ``pumpgrok_orders_total`` from ledger reads (cumulative fills by
side/outcome via ``LedgerStore.read``), not from adapter counters, because
the ledger is the single-writer audit path and adapter counts would
double-count retried placements. Event-time ``note_order`` calls cover the
live path; ``sync_orders`` reconciles from the ledger with delta tracking so
a scrape never double-counts. Unknown breaker states map to 2 (open):
fail-closed beats fail-silent.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

#: Content type for the GET /metrics exposition bytes.
EXPOSITION_CONTENT_TYPE = CONTENT_TYPE_LATEST

#: Verbatim family names (ROADMAP SC2 greps these in source text).
CYCLE_SECONDS = "pumpgrok_cycle_seconds"
BOT_CRASHES_TOTAL = "pumpgrok_bot_crashes_total"
ORDERS_TOTAL = "pumpgrok_orders_total"
EQUITY_SOL = "pumpgrok_equity_sol"
DRAWDOWN_PCT = "pumpgrok_drawdown_pct"
DATA_AGE_SECONDS = "pumpgrok_data_age_seconds"
BREAKER_STATE = "pumpgrok_breaker_state"
KILL_SWITCH = "pumpgrok_kill_switch"
LEDGER_SEQ = "pumpgrok_ledger_seq"

NINE_FAMILIES: tuple[str, ...] = (
    CYCLE_SECONDS,
    BOT_CRASHES_TOTAL,
    ORDERS_TOTAL,
    EQUITY_SOL,
    DRAWDOWN_PCT,
    DATA_AGE_SECONDS,
    BREAKER_STATE,
    KILL_SWITCH,
    LEDGER_SEQ,
)

#: Breaker state text to gauge value (paper-engine 6.6).
_BREAKER_VALUE = {"closed": 0.0, "half-open": 1.0, "open": 2.0}

#: Snapshot keys read by refresh(); see Metrics.refresh docstring.
Snapshot = Mapping[str, Any]


def build_registry() -> CollectorRegistry:
    """Return a fresh registry; never the global default."""
    return CollectorRegistry(auto_describe=True)


class Metrics:
    """The nine OBS-003 families bound to one registry plus a snapshot callable.

    ``snapshot`` returns the scrape-time state mapping with keys
    ``equity_lamports`` (int), ``drawdown_pct`` (float), ``data_age``
    (mapping source -> seconds), ``breakers`` (mapping name -> state text),
    ``kill_switch`` (bool) and ``ledger_seq`` (int). Missing keys leave the
    corresponding gauge untouched.
    """

    def __init__(
        self,
        registry: CollectorRegistry | None = None,
        *,
        snapshot: Callable[[], Snapshot] | None = None,
    ) -> None:
        self._registry = registry if registry is not None else build_registry()
        self._snapshot = snapshot
        self.cycle_seconds = Histogram(
            CYCLE_SECONDS, "Virtual seat cycle seconds.", ["seat"], registry=self._registry
        )
        self.bot_crashes_total = Counter(
            BOT_CRASHES_TOTAL, "Seat cycle crashes.", ["seat"], registry=self._registry
        )
        self.orders_total = Counter(
            ORDERS_TOTAL,
            "Orders by side and outcome.",
            ["side", "outcome"],
            registry=self._registry,
        )
        self.equity_sol = Gauge(
            EQUITY_SOL, "Equity in SOL (lamports/1e9 at scrape).", registry=self._registry
        )
        self.drawdown_pct = Gauge(
            DRAWDOWN_PCT, "Drawdown percent.", registry=self._registry
        )
        self.data_age_seconds = Gauge(
            DATA_AGE_SECONDS, "Data age seconds by source.", ["source"], registry=self._registry
        )
        self.breaker_state = Gauge(
            BREAKER_STATE,
            "Breaker state: 0 closed, 1 half-open, 2 open.",
            ["breaker"],
            registry=self._registry,
        )
        self.kill_switch = Gauge(
            KILL_SWITCH, "Kill switch engaged (0/1).", registry=self._registry
        )
        self.ledger_seq = Gauge(
            LEDGER_SEQ, "Ledger sequence number.", registry=self._registry
        )
        self._last_orders: dict[tuple[str, str], float] = {}
        self._known_sources: set[str] = set()
        self._known_breakers: set[str] = set()

    @property
    def registry(self) -> CollectorRegistry:
        """The registry these families are bound to."""
        return self._registry

    def observe(self, seat: str, duration_s: float, outcome: str) -> None:
        """SeatTask observer: histogram at the last_duration_s site, crash count at the crash site.

        ``outcome`` is ``"ok"`` or ``"crash"`` (the ``run_guarded`` return).
        """
        self.cycle_seconds.labels(seat=seat).observe(max(0.0, duration_s))
        if outcome != "ok":
            self.bot_crashes_total.labels(seat=seat).inc()

    def note_order(self, side: str, outcome: str) -> None:
        """Count one order outcome event (filled|rejected|unknown_result)."""
        self.orders_total.labels(side=side, outcome=outcome).inc()
        self._last_orders[(side, outcome)] = (
            self._last_orders.get((side, outcome), 0.0) + 1.0
        )

    def sync_orders(self, counts: Mapping[tuple[str, str], float]) -> None:
        """Reconcile order counters from cumulative ledger reads without double-counting."""
        for key, total in counts.items():
            side, outcome = key
            delta = max(0.0, float(total) - self._last_orders.get(key, 0.0))
            if delta:
                self.orders_total.labels(side=side, outcome=outcome).inc(delta)
            self._last_orders[key] = float(total)

    def refresh(self) -> None:
        """Set state-snapshot gauges from the injected snapshot callable (scrape time)."""
        if self._snapshot is None:
            return
        snap = self._snapshot
        state = snap()
        if "equity_lamports" in state:
            self.equity_sol.set(float(state["equity_lamports"]) / 1e9)
        if "drawdown_pct" in state:
            self.drawdown_pct.set(float(state["drawdown_pct"]))
        if "kill_switch" in state:
            self.kill_switch.set(1.0 if state["kill_switch"] else 0.0)
        if "ledger_seq" in state:
            self.ledger_seq.set(float(state["ledger_seq"]))
        if "data_age" in state:
            ages = dict(state["data_age"])
            for source in self._known_sources - set(ages):
                self.data_age_seconds.remove(source)
            for source, seconds in ages.items():
                self.data_age_seconds.labels(source=source).set(max(0.0, float(seconds)))
            self._known_sources = set(ages)
        if "breakers" in state:
            states = dict(state["breakers"])
            for name in self._known_breakers - set(states):
                self.breaker_state.remove(name)
            for name, text in states.items():
                self.breaker_state.labels(breaker=name).set(
                    _BREAKER_VALUE.get(str(text), 2.0)
                )
            self._known_breakers = set(states)
        if "orders" in state:
            self.sync_orders(dict(state["orders"]))

    def exposition(self) -> bytes:
        """Render the exposition bytes for GET /metrics (refresh first)."""
        self.refresh()
        return generate_latest(self._registry)
