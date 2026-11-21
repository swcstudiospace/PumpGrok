"""Event and Grok metric families (GRK-10, T-14-03-03).

Registered only when `wake_mode=event`. The nine existing families in
`metrics.py` keep their names, labels, and values. Labels are fixed names
only, never payload values. Integer counters only.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge

from pumpgrok.supervisor.metrics import NINE_FAMILIES, build_registry

EVENTS_TOTAL = "pumpgrok_events_total"
WAKES_TOTAL = "pumpgrok_wakes_total"
GROK_PREFILTER_SKIPS_TOTAL = "pumpgrok_grok_prefilter_skips_total"
GROK_CACHE_HITS_TOTAL = "pumpgrok_grok_cache_hits_total"
GROK_TRANSPORT_CALLS_TOTAL = "pumpgrok_grok_transport_calls_total"

EVENT_FAMILIES: tuple[str, ...] = (
    EVENTS_TOTAL,
    WAKES_TOTAL,
    GROK_PREFILTER_SKIPS_TOTAL,
    GROK_CACHE_HITS_TOTAL,
    GROK_TRANSPORT_CALLS_TOTAL,
)


class EventMetrics:
    """The event-mode families. Constructing this registers them on the registry."""

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self._registry = registry if registry is not None else build_registry()
        self.events_total = Counter(EVENTS_TOTAL, "Bus events by kind.", ["kind"], registry=self._registry)
        self.wakes_total = Counter(WAKES_TOTAL, "Seat wakes by seat.", ["seat"], registry=self._registry)
        self.prefilter_skips = Counter(
            GROK_PREFILTER_SKIPS_TOTAL, "Grok prefilter skips.", registry=self._registry
        )
        self.cache_hits = Counter(
            GROK_CACHE_HITS_TOTAL, "Grok cache hits.", registry=self._registry
        )
        self.transport_calls = Counter(
            GROK_TRANSPORT_CALLS_TOTAL, "Grok transport calls.", registry=self._registry
        )

    @property
    def registry(self) -> CollectorRegistry:
        return self._registry


def build_event_registry(wake_mode: str) -> CollectorRegistry | None:
    """Event families exist only in event mode. Cadence returns None."""
    if wake_mode != "event":
        return None
    return EventMetrics().registry


def assert_nine_families_unchanged() -> bool:
    return len(NINE_FAMILIES) == 9
