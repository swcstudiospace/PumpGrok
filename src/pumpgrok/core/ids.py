"""ULID identity and correlation propagation (interfaces.md 2.3, R29).

The only ULID source in the package. Time comes from the injected Clock, the 80
random bits from the single seeded `random.Random`, so a replay reproduces every
correlation_id byte-for-byte. The `uuid` module is banned in src/pumpgrok.

`Clock` lives here until `replay/clock.py` (plan 01-05) exists; that module will
become the definition site and this one will re-export it.
"""

from __future__ import annotations

import contextvars
import random
from typing import Any, Protocol

from pumpgrok.core.errors import PumpgrokError

ULID_RE = r"^[0-9A-HJKMNP-TV-Z]{26}$"  # Crockford base32, 48-bit ms time + 80-bit rng


class Clock(Protocol):
    """The only time source. Every id, audit row, timeout and retry wait reads it."""

    def now(self) -> float: ...  # epoch seconds (UTC)

    def monotonic(self) -> float: ...

    def utc_iso(self) -> str: ...

    async def sleep(self, seconds: float) -> None: ...

    def timeout(self, seconds: float) -> Any: ...  # async context manager; virtual in replay


class IdFactory:
    """The only ULID source in the package (R29).

    Monotonic within an instance: if the clock stands still (or regresses) and the
    fresh random bits would repeat or go backwards, the previous value is bumped by
    one, per the ULID spec. Deterministic for a fixed (clock, rng) call sequence.
    """

    def __init__(self, clock: Clock, rng: random.Random) -> None:
        self._clock = clock
        self._rng = rng
        self._last = 0

    def ulid(self) -> str:
        ms = int(self._clock.now() * 1000)
        candidate = (ms << 80) | self._rng.getrandbits(80)
        if candidate <= self._last:
            candidate = self._last + 1
        self._last = candidate
        return _crockford(candidate, 26)


_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _crockford(value: int, width: int) -> str:
    out = []
    for _ in range(width):
        out.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(out))


class CorrelationId(str):
    """Opaque id spanning signal -> decision -> order -> fill.

    The root is a ULID; child spans are `<ulid>.<n>` with `n` the 1-based span
    counter of the root's dynamic extent. The ledger `correlation_id` column
    stores the root.
    """

    __slots__ = ()

    @classmethod
    def new(cls, ids: IdFactory) -> CorrelationId:
        return cls(ids.ulid())

    @property
    def root(self) -> str:
        return self.split(".", 1)[0]

    def child(self, n: int) -> CorrelationId:
        return CorrelationId(f"{self.root}.{n}")


_correlation: contextvars.ContextVar[CorrelationId | None] = contextvars.ContextVar(
    "pumpgrok_correlation", default=None
)
_span_counter: contextvars.ContextVar[int] = contextvars.ContextVar("pumpgrok_span", default=0)


def current_correlation() -> CorrelationId:
    """Return the ambient id. An unbound call is a programming error, never a silent new id."""
    cid = _correlation.get()
    if cid is None:
        raise PumpgrokError("no correlation id bound")
    return cid


def next_span(cid: CorrelationId) -> CorrelationId:
    n = _span_counter.get() + 1
    _span_counter.set(n)
    return cid.child(n)


class bind_correlation:
    """Bind an id for the dynamic extent of a bot cycle or tool call."""

    def __init__(self, cid: CorrelationId) -> None:
        self._cid = cid
        self._token: contextvars.Token[CorrelationId | None] | None = None

    def __enter__(self) -> CorrelationId:
        self._token = _correlation.set(self._cid)
        return self._cid

    def __exit__(self, *exc: object) -> None:
        assert self._token is not None
        _correlation.reset(self._token)
