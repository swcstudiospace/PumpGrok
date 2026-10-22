"""Span timing for every tool call (OBS-003, INV-S-13).

A span is a dual sync/async context manager: ``with span(...)`` and
``async with span(...)`` both work. The parent name and nesting depth live
in contextvars, so spans nest across awaits. Duration comes from the
injected :class:`Clock` only; wall-clock sources are banned in this package
(``tests/safety/test_static_guards.py`` enforces it).

Clock-binding choice (05-PATTERNS 2.1, lower-risk reading): the locked
signature ``span(name, **fields)`` carries no clock, so the clock is bound
in a contextvar by the caller -- the registry wrapper binds it next to
``bind_correlation`` -- mirroring the correlation pattern. Entering a span
without a bound clock raises instead of reading wall time.

Emission goes through the regular ``extra`` mechanism (``log.info`` with
``event="span"``), so :class:`RedactionFilter` still applies; the handler
is never bypassed.
"""

from __future__ import annotations

import contextvars
import logging
from typing import TYPE_CHECKING, Any

from pumpgrok.core.errors import PumpgrokError
from pumpgrok.core.ids import ambient_correlation

if TYPE_CHECKING:
    from pumpgrok.core.ids import Clock

log = logging.getLogger("pumpgrok.spans")

#: Clock bound by the registry/supervisor for the dynamic extent of a cycle.
_CLOCK: contextvars.ContextVar[Clock | None] = contextvars.ContextVar(
    "pumpgrok_span_clock", default=None
)
#: Name of the enclosing span, if any.
_PARENT: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "pumpgrok_span_parent", default=None
)
#: Nesting depth of the current span stack.
_DEPTH: contextvars.ContextVar[int] = contextvars.ContextVar("pumpgrok_span_depth", default=0)


class bind_clock:
    """Bind a Clock for the dynamic extent of a span tree (mirrors bind_correlation)."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._token: contextvars.Token[Clock | None] | None = None

    def __enter__(self) -> Clock:
        self._token = _CLOCK.set(self._clock)
        return self._clock

    def __exit__(self, *exc: object) -> None:
        assert self._token is not None
        _CLOCK.reset(self._token)


def current_clock() -> Clock:
    """Return the bound clock. An unbound span extent is a programming error."""
    clock = _CLOCK.get()
    if clock is None:
        raise PumpgrokError("no span clock bound")
    return clock


class _Span:
    """One timed span; enter with ``with`` or ``async with``."""

    def __init__(self, name: str, fields: dict[str, Any]) -> None:
        self._name = name
        self._fields = fields
        self._start = 0.0
        self._tokens: tuple[
            contextvars.Token[str | None], contextvars.Token[int]
        ] | None = None

    def _enter(self) -> _Span:
        clock = current_clock()
        self._start = clock.now()
        parent = _PARENT.get()
        self._tokens = (_PARENT.set(self._name), _DEPTH.set(_DEPTH.get() + 1))
        self._parent = parent
        return self

    def _exit(self) -> None:
        assert self._tokens is not None
        elapsed_s = max(0.0, current_clock().now() - self._start)
        cid = ambient_correlation()
        log.info(
            "span",
            extra={
                "event": "span",
                "duration_ms": round(elapsed_s * 1000.0, 3),
                "span": self._name,
                "parent": self._parent,
                "depth": _DEPTH.get(),
                "correlation_id": None if cid is None else str(cid),
                **self._fields,
            },
        )
        parent_token, depth_token = self._tokens
        _DEPTH.reset(depth_token)
        _PARENT.reset(parent_token)
        self._tokens = None

    def __enter__(self) -> _Span:
        return self._enter()

    def __exit__(self, *exc: object) -> None:
        self._exit()

    async def __aenter__(self) -> _Span:
        return self._enter()

    async def __aexit__(self, *exc: object) -> None:
        self._exit()


def span(name: str, **fields: Any) -> _Span:
    """Open a timed span emitting ``event="span"`` with the virtual-clock duration."""
    return _Span(name, fields)
