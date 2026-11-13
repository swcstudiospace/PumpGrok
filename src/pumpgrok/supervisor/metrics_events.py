"""Event-mode metric families: bus and Grok gateway observations (EVT-12, GRK-10).

Registered only when the supervisor runs in event mode (``Metrics(event_mode=True)``), on the
same registry and the same GET /metrics endpoint as the nine cadence families. Those keep their
bytes, and cadence mode never creates these collectors, so its exposition does not change.

Families (names verbatim):

- ``pumpgrok_events_total{kind,outcome}`` counter: bus handler attempts. ``outcome`` is
  ``delivered`` or ``failed``. An attempt cancelled at shutdown is counted as neither.
- ``pumpgrok_event_dlq_total{kind}`` counter: events handed to the dead-letter queue. Counted only
  after the handoff returns, so a failed handoff that the bus retries is not counted early.
- ``pumpgrok_grok_calls_total{agent,outcome}`` counter: charged transport calls. ``outcome`` is
  ``ok`` for a text reply and ``error`` for any other exit, including a deadline cancel. Cache
  hits, prefilter skips and budget refusals never reach the transport and are not counted here.

The observers wrap the seams the real bus and gateway already take: the bus handler and DLQ
callables, and the gateway transport. A wrapper never changes a result or an exception.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import TYPE_CHECKING, Protocol, TypeVar

from prometheus_client import CollectorRegistry, Counter

if TYPE_CHECKING:
    from pumpgrok.events.bus import Dlq, Handler
    from pumpgrok.events.models import Event

#: Verbatim family names.
EVENTS_TOTAL = "pumpgrok_events_total"
EVENT_DLQ_TOTAL = "pumpgrok_event_dlq_total"
GROK_CALLS_TOTAL = "pumpgrok_grok_calls_total"

EVENT_FAMILIES: tuple[str, ...] = (EVENTS_TOTAL, EVENT_DLQ_TOTAL, GROK_CALLS_TOTAL)


class _Request(Protocol):
    """The one field the observer reads from a gateway request: the agent label."""

    @property
    def agent(self) -> str: ...


_RC_contra = TypeVar("_RC_contra", bound=_Request, contravariant=True)


class _Transport(Protocol[_RC_contra]):
    """The gateway transport seam as the observer sees it: a call that returns response text."""

    async def __call__(self, request: _RC_contra, text: str) -> str: ...


class EventCollectors:
    """The three event-mode counters bound to one registry, and their observer wrappers."""

    def __init__(self, registry: CollectorRegistry) -> None:
        self._registry = registry
        self.events_total = Counter(
            EVENTS_TOTAL,
            "Bus handler attempts by kind and outcome.",
            ["kind", "outcome"],
            registry=registry,
        )
        self.event_dlq_total = Counter(
            EVENT_DLQ_TOTAL,
            "Events handed to the dead-letter queue by kind.",
            ["kind"],
            registry=registry,
        )
        self.grok_calls_total = Counter(
            GROK_CALLS_TOTAL,
            "Charged Grok transport calls by agent and outcome.",
            ["agent", "outcome"],
            registry=registry,
        )

    @property
    def registry(self) -> CollectorRegistry:
        """The registry these families are bound to."""
        return self._registry

    def observe_handler(self, handler: Handler) -> Handler:
        """Wrap a bus handler: count each attempt as delivered, or failed then re-raise."""

        async def observed(event: Event) -> None:
            try:
                await handler(event)
            except Exception:
                self.events_total.labels(kind=event.kind.value, outcome="failed").inc()
                raise
            self.events_total.labels(kind=event.kind.value, outcome="delivered").inc()

        return observed

    def observe_dlq(self, dlq: Dlq) -> Dlq:
        """Wrap a bus DLQ callable: count an event once its handoff has returned."""

        def observed(event: Event) -> Awaitable[None] | None:
            result = dlq(event)
            if result is None:
                self._count_dlq(event)
                return None
            return self._await_dlq(result, event)

        return observed

    async def _await_dlq(self, pending: Awaitable[None], event: Event) -> None:
        await pending
        self._count_dlq(event)

    def _count_dlq(self, event: Event) -> None:
        self.event_dlq_total.labels(kind=event.kind.value).inc()

    def observe_transport[R: _Request](self, transport: _Transport[R]) -> _Transport[R]:
        """Wrap the gateway transport: every call it is charged for is counted once."""
        return _ObservedTransport(transport, self.grok_calls_total)


class _ObservedTransport[R: _Request]:
    """A transport that counts each call it forwards."""

    def __init__(self, inner: _Transport[R], calls: Counter) -> None:
        self._inner = inner
        self._calls = calls

    async def __call__(self, request: R, text: str) -> str:
        try:
            response = await self._inner(request, text)
        except BaseException:
            self._calls.labels(agent=request.agent, outcome="error").inc()
            raise
        outcome = "ok" if isinstance(response, str) else "error"
        self._calls.labels(agent=request.agent, outcome=outcome).inc()
        return response
