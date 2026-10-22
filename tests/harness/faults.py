"""Deterministic degraded-mode injection over replay fixture events.

Each mode fires at one event index so a test can place the fault exactly. Injected
errors subclass `InjectedFault`, so a product error can never be mistaken for one.
`TIMEOUT` raises the builtin `TimeoutError`, the type product code must already handle.

Protocol fakes (`FaultyLLMClient`, `FaultyRpcClient`, `FaultyDataSource`,
`FaultyPriceSource`, `FaultyExecutionAdapter`, `FaultyLedgerStore`) stand in at
the exact seams named in 05-PATTERNS 2.11 (core/llm.py, tools/onchain/rpc.py,
core/datasource.py, execution/paper_adapter.py, core/adapter.py, ledger/store.py).
Every fake counts how often the fault fired so a test asserts the fault fired
first and never mistakes a passing recovery for an unfired fault.
"""

from __future__ import annotations

import errno
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import IO, Any

from pumpgrok.core.errors import DataStale
from pumpgrok.replay.clock import format_ts_utc, parse_ts_utc
from pumpgrok.tools.onchain.rpc import RpcError


class FaultMode(StrEnum):
    STALE = "stale"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    RAISE = "raise"
    UNWRITABLE = "unwritable"
    MALFORMED = "malformed"
    UNKNOWN = "unknown"


class InjectedFault(RuntimeError):
    """Raised by FaultMode.RAISE."""


class InjectedRateLimit(InjectedFault):
    """Raised by FaultMode.RATE_LIMIT; mirrors an HTTP 429 with a retry hint."""

    status = 429

    def __init__(self, retry_after_s: float) -> None:
        super().__init__("injected rate limit")
        self.retry_after_s = retry_after_s


class InjectedUnknown(InjectedFault):
    """Raised by FaultMode.UNKNOWN: the attempt outcome is unknown, never retried."""

class FaultInjector:
    """Apply one fault at `at_index` of an event stream, or to a write sink.

    STALE rewinds that event's `ts_utc` by `stale_by_s` and marks it `fault: stale`, so
    freshness checks downstream see old data. TIMEOUT, RATE_LIMIT, RAISE and UNKNOWN
    raise at that index after the earlier events have been yielded. MALFORMED yields
    the event with an unparsable `ts_utc` (plus `fault: malformed`) so the manifest
    loader refuses it as a corrupt fixture. UNWRITABLE leaves events untouched and
    makes `open_sink` fail with EACCES.
    """

    def __init__(
        self,
        mode: FaultMode,
        *,
        at_index: int = 0,
        stale_by_s: float = 3600.0,
        retry_after_s: float = 1.0,
    ) -> None:
        if at_index < 0:
            raise ValueError("at_index must be non-negative")
        self._mode = mode
        self._at = at_index
        self._stale_by_s = stale_by_s
        self._retry_after_s = retry_after_s

    @property
    def mode(self) -> FaultMode:
        return self._mode

    def apply(self, events: Iterable[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        for index, event in enumerate(events):
            if index != self._at:
                yield event
                continue
            if self._mode is FaultMode.STALE:
                stale = dict(event)
                stamp = parse_ts_utc(str(event["ts_utc"])) - self._stale_by_s
                stale["ts_utc"] = format_ts_utc(stamp)
                stale["fault"] = FaultMode.STALE.value
                yield stale
            elif self._mode is FaultMode.TIMEOUT:
                raise TimeoutError("injected upstream timeout")
            elif self._mode is FaultMode.RATE_LIMIT:
                raise InjectedRateLimit(self._retry_after_s)
            elif self._mode is FaultMode.RAISE:
                raise InjectedFault("injected fault")
            elif self._mode is FaultMode.UNKNOWN:
                raise InjectedUnknown("injected unknown result; never retried")
            elif self._mode is FaultMode.MALFORMED:
                corrupt = dict(event)
                corrupt["ts_utc"] = "malformed"
                corrupt["fault"] = FaultMode.MALFORMED.value
                yield corrupt
            else:
                yield event

    @contextmanager
    def open_sink(self, path: Path) -> Iterator[IO[str]]:
        """Open `path` for appending, or fail with EACCES in UNWRITABLE mode."""
        if self._mode is FaultMode.UNWRITABLE:
            raise PermissionError(errno.EACCES, "injected: sink is unwritable", str(path))
        with path.open("a", encoding="utf-8") as fh:
            yield fh


class FaultyLLMClient:
    """Stand-in for the model-resolution seam (core/llm.py GrokOps callers).

    `complete` mirrors `ReplayLlm.complete(request, clock)`: one recorded
    outcome per call, virtual latency applied by the caller. The fault fires
    once at `at_call`; later calls answer ok. TIMEOUT raises builtin
    `TimeoutError`, the type product code already handles; every other
    injected error subclasses `InjectedFault`.
    """

    def __init__(
        self,
        mode: FaultMode,
        *,
        at_call: int = 0,
        latency_s: float = 1.9,
        retry_after_s: float = 1.0,
    ) -> None:
        if at_call < 0:
            raise ValueError("at_call must be non-negative")
        self._mode = mode
        self._at = at_call
        self._latency_s = latency_s
        self._retry_after_s = retry_after_s
        self.calls: list[dict[str, Any]] = []
        self.fired = 0

    async def complete(
        self, request: Mapping[str, Any], clock: Any
    ) -> dict[str, Any]:
        """Answer one model-resolution request, faulting once at `at_call`."""
        index = len(self.calls)
        self.calls.append(dict(request))
        if index != self._at:
            return {"outcome": "ok", "response": {"verdict": "skip"}, "latency_s": 0.0}
        self.fired += 1
        if self._mode is FaultMode.TIMEOUT:
            raise TimeoutError("injected LLM timeout")
        if self._mode is FaultMode.RATE_LIMIT:
            raise InjectedRateLimit(self._retry_after_s)
        if self._mode is FaultMode.RAISE:
            raise InjectedFault("injected LLM 503")
        if self._mode is FaultMode.MALFORMED:
            return {"outcome": "malformed", "response": "not json{{{", "latency_s": 0.0}
        if self._mode is FaultMode.UNKNOWN:
            raise InjectedUnknown("injected LLM unknown result; never retried")
        raise InjectedFault(f"injected LLM fault mode={self._mode.value}")


class FaultyRpcClient:
    """Stand-in for the RPC seam (tools/onchain/rpc.py RpcClient.call).

    One mode per endpoint in failover order; `None` means that endpoint
    answers ok. Mirrors the product contract: timeouts, 5xx and 429 fail
    over to the next endpoint, a malformed body counts toward DataStale,
    an unknown result raises immediately without failover. When every
    endpoint fails the product errors surface: `RpcError`, or `DataStale`
    when every endpoint was malformed.
    """

    def __init__(
        self, modes: list[FaultMode | None], *, retry_after_s: float = 1.0
    ) -> None:
        if not modes:
            raise ValueError("modes must list at least one endpoint")
        self._modes = list(modes)
        self._retry_after_s = retry_after_s
        self.attempts: list[int] = []
        self.fired = 0

    @property
    def endpoint_count(self) -> int:
        """Number of configured endpoints."""
        return len(self._modes)

    async def call(self, method: str, params: list[Any]) -> Any:
        """POST `method` to each endpoint in order; first success wins."""
        bad_bodies = 0
        for index, mode in enumerate(self._modes):
            self.attempts.append(index)
            if mode is None:
                return {"result": "ok", "endpoint": index}
            self.fired += 1
            if mode is FaultMode.RATE_LIMIT:
                continue
            if mode is FaultMode.TIMEOUT:
                continue
            if mode is FaultMode.RAISE:
                continue
            if mode is FaultMode.MALFORMED:
                bad_bodies += 1
                continue
            if mode is FaultMode.UNKNOWN:
                raise InjectedUnknown("injected RPC unknown result; never retried")
            if mode is FaultMode.STALE:
                continue
            if mode is FaultMode.UNWRITABLE:
                continue
        if bad_bodies == len(self._modes):
            raise DataStale(
                f"rpc bad body method={method} endpoints={len(self._modes)}"
            )
        raise RpcError(f"rpc failed method={method} endpoints={len(self._modes)}")


class FaultyDataSource:
    """Stand-in for the DataSource protocol (core/datasource.py).

    Follows the protocol rule: `fetch` never raises on upstream failure
    while a last-good value exists (it returns the cached value with
    `Freshness.stale is True`); it raises product `DataStale` only when no
    cache exists, and `DataBlind` for malformed payloads with no last-good.
    """

    def __init__(
        self,
        mode: FaultMode,
        *,
        name: str = "pumpfun_rest",
        last_good: Any = None,
    ) -> None:
        self.name = name
        self.rate_limit_key = name
        self._mode = mode
        self._last_good = last_good
        self.fetches = 0
        self.fired = 0

    def _freshness(self, *, stale: bool) -> Any:
        from pumpgrok.core.datasource import Freshness

        age = 121.0 if stale else 0.0
        return Freshness(
            fetched_at=datetime.now(UTC), age_s=age, max_age_s=120.0
        )

    async def fetch(
        self, request: Mapping[str, Any], *, max_age_s: float
    ) -> tuple[Any, Any]:
        """Return the cached value with a stale marker, or raise DataStale."""
        self.fetches += 1
        if self._mode is FaultMode.STALE:
            self.fired += 1
            if self._last_good is None:
                raise DataStale("injected: no last-good value")
            return self._last_good, self._freshness(stale=True)
        if self._mode is FaultMode.RAISE:
            self.fired += 1
            raise DataStale("injected: no last-good value")
        if self._mode is FaultMode.TIMEOUT:
            self.fired += 1
            raise TimeoutError("injected data-source timeout")
        if self._mode is FaultMode.MALFORMED:
            self.fired += 1
            return {"reserves": "NaN", "mint": "x"}, self._freshness(stale=True)
        return {"tick": dict(request)}, self._freshness(stale=False)

    def freshness(self, key: str) -> Any:
        """Last observed freshness for `key`; None before any fetch."""
        if not self.fetches:
            return None
        return self._freshness(stale=self._mode is not FaultMode.STALE)

    async def health(self) -> Any:
        """Degraded while faulted, ok otherwise."""
        from pumpgrok.core.datasource import Health, HealthStatus

        status = HealthStatus.DOWN if self.fired else HealthStatus.OK
        return Health(
            status=status,
            checked_at=datetime.now(UTC),
            consecutive_failures=self.fired,
        )

    async def aclose(self) -> None:
        """Release nothing; the fake holds no transport."""


class FaultyPriceSource:
    """Stand-in for the PriceSource protocol (execution/paper_adapter.py).

    `curve` answers the last-good snapshot while stale, `None` when no
    cache exists, and raises `InjectedFault` for hard failures so the
    fault is never mistaken for a product error.
    """

    def __init__(self, mode: FaultMode, *, last_good: Any = None) -> None:
        self._mode = mode
        self._last_good = last_good
        self.reads = 0
        self.fired = 0

    async def curve(self, mint: str) -> Any:
        """Curve snapshot for `mint`: last-good while stale, None without cache."""
        self.reads += 1
        if self._mode is FaultMode.STALE:
            self.fired += 1
            return self._last_good
        if self._mode is FaultMode.RAISE:
            self.fired += 1
            raise InjectedFault("injected price-source failure")
        if self._mode is FaultMode.TIMEOUT:
            self.fired += 1
            raise TimeoutError("injected price-source timeout")
        if self._mode is FaultMode.MALFORMED:
            self.fired += 1
            return {"mint": mint, "s_lamports": "NaN"}
        if self._mode is FaultMode.UNKNOWN:
            self.fired += 1
            raise InjectedUnknown("injected price unknown result; never retried")
        from pumpgrok.execution.paper_adapter import CurveSnapshot

        return CurveSnapshot(mint=mint, s_lamports=42_000_000_000, t_units=766_428_571)


class FaultyExecutionAdapter:
    """Stand-in for the ExecutionAdapter protocol (core/adapter.py).

    UNKNOWN raises `InjectedUnknown` exactly once per call and never
    retries internally (`places` grows by one per call); the caller owns
    the single-send rule. TIMEOUT raises builtin `TimeoutError`.
    """

    mode = "paper"
    venue = "paper"

    def __init__(self, mode: FaultMode = FaultMode.UNKNOWN) -> None:
        self._mode = mode
        self.places: list[Any] = []
        self.cancels: list[str] = []
        self.fired = 0

    async def place(self, request: Any) -> Any:
        """Place one order: unknown unless the mode says otherwise."""
        self.places.append(request)
        self.fired += 1
        if self._mode is FaultMode.UNKNOWN:
            raise InjectedUnknown("injected unknown result; never retried")
        if self._mode is FaultMode.TIMEOUT:
            raise TimeoutError("injected execution timeout")
        raise InjectedFault(f"injected execution fault mode={self._mode.value}")

    async def cancel(self, order_id: str, ticket_id: str, decision_id: str) -> bool:
        """Record the cancel; the fake never holds an order."""
        self.cancels.append(order_id)
        return False


class FaultyLedgerStore:
    """Wraps a real LedgerStore; UNWRITABLE refuses appends with EACCES.

    Reads delegate to the inner store, so verification and folds keep
    working while writes are refused. RAISE fails appends with
    `InjectedFault` instead.
    """

    def __init__(self, inner: Any, mode: FaultMode = FaultMode.UNWRITABLE) -> None:
        self._inner = inner
        self._mode = mode
        self.fired = 0

    def append(self, **kwargs: Any) -> Any:
        """Append one row, or refuse when the fault is armed."""
        if self._mode is FaultMode.UNWRITABLE:
            self.fired += 1
            raise PermissionError(errno.EACCES, "injected: sink is unwritable", "ledger")
        if self._mode is FaultMode.RAISE:
            self.fired += 1
            raise InjectedFault("injected ledger failure")
        return self._inner.append(**kwargs)

    def append_batch(self, rows: Any) -> Any:
        """Append many rows, or refuse when the fault is armed."""
        if self._mode is FaultMode.UNWRITABLE:
            self.fired += 1
            raise PermissionError(errno.EACCES, "injected: sink is unwritable", "ledger")
        if self._mode is FaultMode.RAISE:
            self.fired += 1
            raise InjectedFault("injected ledger failure")
        return self._inner.append_batch(rows)

    def __getattr__(self, name: str) -> Any:
        """Delegate reads (verify, read, count, close) to the inner store."""
        return getattr(self.__dict__["_inner"], name)
