"""run --record session and live serve paper cycles.

The dataset recorder lives at the dataset directory. Portal and logs frames are
recorded before they are pumped, and the clock is pinned to the frame's arrival
ts for the whole pump, so each observation is stamped with that ts rather than
a later processing time. Exactly one config frame records the WatchSet capacity.
getTransaction responses are recorded by the JSON-RPC wrapper during the pump,
at that same ts.
"""

from __future__ import annotations

import asyncio
import signal
import tempfile
from collections import deque
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, closing
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.datafeed import transport as feed_transport
from pumpgrok.datafeed.bridge import build_observation_bridge
from pumpgrok.datafeed.logs import PUMP_PROGRAM_ID, LogsFeed
from pumpgrok.datafeed.mintbook import MintBook
from pumpgrok.datafeed.portal import PortalFeed
from pumpgrok.datafeed.readonly import ReadOnlyBoundary, ReadTransport
from pumpgrok.datafeed.resync import RollingWindowLimiter
from pumpgrok.datafeed.transport import Arrival, RecordingJsonRpc, read_arrivals
from pumpgrok.datafeed.watchset import WatchSet
from pumpgrok.events.models import Event
from pumpgrok.events.sources import SourceSupervisor
from pumpgrok.replay.clock import Clock, format_ts_utc
from pumpgrok.replay.live_recorder import (
    CONFIG_STREAM,
    LOGS_STREAM,
    PORTAL_STREAM,
    LiveRecorder,
)
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.limits import EngineLimits
from pumpgrok.supervisor.live_paper import build_live_paper_root

# The WatchSet capacity a recording admits with. One config frame persists it.
WATCH_CAPACITY = 64
_POLL_S = 0.05
_RATE_LIMIT = 10_000
_RATE_WINDOW_S = 10.0
_MAX_AGE_S = 10.0
_MAX_OBSERVATIONS = 4
_INBOX_DEPTH = 16


class PinnedClock:
    """A clock whose ``now`` stays at the frame arrival ts until ``release``."""

    def __init__(self, inner: Clock) -> None:
        self._inner = inner
        self._pinned: float | None = None

    def pin(self, ts: float) -> None:
        self._pinned = ts

    def release(self) -> None:
        self._pinned = None

    def now(self) -> float:
        if self._pinned is not None:
            return self._pinned
        return self._inner.now()

    def monotonic(self) -> float:
        return self._inner.monotonic()

    def utc_iso(self) -> str:
        return format_ts_utc(self.now())

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)

    def timeout(self, seconds: float) -> AbstractAsyncContextManager[None]:
        return self._inner.timeout(seconds)


def recorder_factory(dataset_dir: Path, *, clock: Clock) -> LiveRecorder:
    """Default dataset recorder. Tests replace this to log call order."""
    return LiveRecorder(dataset_dir, clock=clock)


def _ws_url(endpoint: str) -> str:
    """The websocket form of an https RPC endpoint. Query and userinfo are dropped."""
    parts = urlsplit(endpoint)
    scheme = "wss" if parts.scheme == "https" else parts.scheme
    return urlunsplit((scheme, parts.netloc, parts.path, "", ""))


def _portal_allowed(payload: dict[str, object], mints: frozenset[str] | None) -> bool:
    """True when the portal frame may be admitted. A filter drops every other mint."""
    if mints is None:
        return True
    mint = payload.get("mint")
    return isinstance(mint, str) and mint in mints


class _PushFrames:
    """One frame is pushed, then pump_once reads it. An empty pull is a programming error."""

    def __init__(self) -> None:
        self._pending: deque[object] = deque()

    def push(self, frame: object) -> None:
        self._pending.append(frame)

    async def next_frame(self) -> object:
        if not self._pending:
            raise AssertionError("pump_once with no pushed frame")
        return self._pending.popleft()

    async def reconnect(self) -> None:
        return None


async def _no_event_consumers(_event: Event) -> None:
    """Curve ticks reach the dataset through the recorder, not an event consumer."""


def _refuse_dead_letter(event: Event) -> None:
    raise RuntimeError(f"record session has no dead-letter sink for {event.kind}")


def _take_next(inboxes: dict[str, asyncio.Queue[Arrival]], last: str) -> Arrival | None:
    """The next queued arrival. The socket after ``last`` goes first, so a burst on one socket
    yields to the other on every turn."""
    other = LOGS_STREAM if last == PORTAL_STREAM else PORTAL_STREAM
    for stream in (other, last):
        inbox = inboxes[stream]
        if not inbox.empty():
            return inbox.get_nowait()
    return None


async def _wait_for_arrival(wake: asyncio.Event, clock: PinnedClock, seconds: float) -> None:
    """Wait until a reader queues an arrival, or ``seconds`` pass on ``clock``."""
    try:
        async with clock.timeout(seconds):
            await wake.wait()
    except TimeoutError:
        return


async def _aclose(agen: AsyncIterator[object]) -> None:
    """Close an async generator. aiter() is typed as AsyncIterator, which has no aclose."""
    close = getattr(agen, "aclose", None)
    if close is None:
        return
    await close()


async def _apply(
    feed: PortalFeed | LogsFeed,
    frames: _PushFrames,
    payload: dict[str, object],
) -> None:
    frames.push(payload)
    await feed.pump_once()


async def _pump(
    *,
    clock: PinnedClock,
    arrivals: Clock,
    deadline: float,
    portal: PortalFeed,
    logs: LogsFeed,
    recorder: LiveRecorder,
    portal_frames: _PushFrames,
    logs_frames: _PushFrames,
    portal_socket: AsyncIterator[object],
    logs_socket: AsyncIterator[object],
    mints: frozenset[str] | None,
) -> None:
    """Feed each arrival to its feed, alternating between sockets, until the deadline or both end.

    Each socket is drained by its own reader task into its own bounded inbox. When both have
    arrivals queued, the turn passes to the other socket, so a burst on one cannot run ahead
    of the other. A quiet poll never cancels a socket. A frame is recorded and pumped while the
    clock is pinned to its arrival ts, and the pin releases before the next arrival is taken.
    """
    wake = asyncio.Event()
    inboxes: dict[str, asyncio.Queue[Arrival]] = {
        PORTAL_STREAM: asyncio.Queue(maxsize=_INBOX_DEPTH),
        LOGS_STREAM: asyncio.Queue(maxsize=_INBOX_DEPTH),
    }
    readers = [
        asyncio.create_task(
            read_arrivals(
                portal_socket,
                stream=PORTAL_STREAM,
                now=arrivals.now,
                inbox=inboxes[PORTAL_STREAM],
                wake=wake,
            )
        ),
        asyncio.create_task(
            read_arrivals(
                logs_socket,
                stream=LOGS_STREAM,
                now=arrivals.now,
                inbox=inboxes[LOGS_STREAM],
                wake=wake,
            )
        ),
    ]
    open_streams = {PORTAL_STREAM, LOGS_STREAM}
    last = LOGS_STREAM
    try:
        while open_streams:
            remaining = deadline - clock.monotonic()
            if remaining <= 0:
                break
            arrival = _take_next(inboxes, last)
            if arrival is None:
                await _wait_for_arrival(wake, clock, min(_POLL_S, remaining))
                wake.clear()
                continue
            last = arrival.stream
            payload = arrival.payload
            if payload is None:
                if arrival.failure is not None:
                    raise arrival.failure
                open_streams.discard(arrival.stream)
                continue
            clock.pin(arrival.ts)
            try:
                recorder.record_frame({"stream": arrival.stream, "payload": payload})
                if arrival.stream != PORTAL_STREAM:
                    await _apply(logs, logs_frames, payload)
                elif _portal_allowed(payload, mints):
                    await _apply(portal, portal_frames, payload)
            finally:
                clock.release()
    finally:
        for reader in readers:
            reader.cancel()
        await asyncio.gather(*readers, return_exceptions=True)
        await _aclose(portal_socket)
        await _aclose(logs_socket)


async def _record_session(
    dataset_dir: Path,
    *,
    duration_s: float,
    mints: frozenset[str] | None,
    clock: Clock,
    transport: ReadTransport,
    recorder_factory: Callable[..., LiveRecorder],
    endpoint: str,
    budget: RiskBudget,
    limits: EngineLimits,
    rng_seed: int,
    max_age_s: float,
    max_observations: int,
    portal_ws_url: str,
) -> Path:
    pinned = PinnedClock(clock)
    recorder = recorder_factory(dataset_dir, clock=pinned)
    recorder.record_frame({"stream": CONFIG_STREAM, "payload": {"watch_capacity": WATCH_CAPACITY}})
    rpc = RecordingJsonRpc(endpoint, transport, recorder, pinned)
    started = pinned.monotonic()
    deadline = started + duration_s
    with tempfile.TemporaryDirectory() as scratch:
        scratch_path = Path(scratch)
        root = await build_live_paper_root(
            mode="paper",
            endpoint=endpoint,
            transport=rpc,
            clock=pinned,
            rng_seed=rng_seed,
            data_dir=scratch_path,
            budget=budget,
            limits=limits,
            max_age_s=max_age_s,
            max_observations=max_observations,
        )
        try:
            boundary = ReadOnlyBoundary(endpoint=endpoint, transport=rpc)
            limiter = RollingWindowLimiter(pinned, limit=_RATE_LIMIT, window_s=_RATE_WINDOW_S)
            watch = WatchSet(max_watched_mints=WATCH_CAPACITY)
            mintbook = MintBook(watch=watch)
            bridge = build_observation_bridge(
                clock=pinned,
                handler=_no_event_consumers,
                dlq=_refuse_dead_letter,
                recorder=recorder,
                price=root.prices,
            )
            portal_frames, logs_frames = _PushFrames(), _PushFrames()
            cursor = scratch_path / "feed-cursor.sqlite"
            with closing(SourceSupervisor(pinned, make_rng(rng_seed), path=cursor)) as supervisor:
                portal = PortalFeed(
                    boundary=boundary,
                    frames=portal_frames,
                    clock=pinned,
                    supervisor=supervisor,
                    mintbook=mintbook,
                    bridge=bridge,
                    limiter=limiter,
                )
                logs = LogsFeed(
                    boundary=boundary,
                    frames=logs_frames,
                    clock=pinned,
                    supervisor=supervisor,
                    watch=watch,
                    bridge=bridge,
                    limiter=limiter,
                )
                await _pump(
                    clock=pinned,
                    arrivals=clock,
                    deadline=deadline,
                    portal=portal,
                    logs=logs,
                    recorder=recorder,
                    portal_frames=portal_frames,
                    logs_frames=logs_frames,
                    portal_socket=feed_transport.open_websocket(
                        portal_ws_url, stream=PORTAL_STREAM
                    ),
                    logs_socket=feed_transport.open_websocket(
                        _ws_url(endpoint), stream=LOGS_STREAM
                    ),
                    mints=mints,
                )
            recorder.seal(portal.gaps, logs.gaps)
        finally:
            root.close()
    return dataset_dir


def record_session(
    dataset_dir: Path,
    *,
    duration_s: float,
    mints: frozenset[str] | None,
    clock: Clock,
    transport: ReadTransport,
    recorder_factory: Callable[..., LiveRecorder],
    endpoint: str,
    budget: RiskBudget,
    limits: EngineLimits,
    rng_seed: int = 0,
    max_age_s: float = _MAX_AGE_S,
    max_observations: int = _MAX_OBSERVATIONS,
    portal_ws_url: str | None = None,
) -> Path:
    """Record a paper session into ``dataset_dir`` and seal it.

    Runs for ``duration_s`` on ``clock``, or until both frame sources end.
    Returns the sealed directory.
    """
    if isinstance(duration_s, bool) or not isinstance(duration_s, (int, float)) or duration_s <= 0:
        raise ValueError("duration_s must be positive")
    portal_url = portal_ws_url if portal_ws_url is not None else _ws_url(endpoint)
    return asyncio.run(
        _record_session(
            dataset_dir,
            duration_s=float(duration_s),
            mints=mints,
            clock=clock,
            transport=transport,
            recorder_factory=recorder_factory,
            endpoint=endpoint,
            budget=budget,
            limits=limits,
            rng_seed=rng_seed,
            max_age_s=max_age_s,
            max_observations=max_observations,
            portal_ws_url=portal_url,
        )
    )


async def _paper_cycle(root: object) -> None:
    """One paper cycle: the two portal subscriptions and one logs subscription."""
    boundary = root.boundary  # type: ignore[attr-defined]
    await boundary.portal("subscribeNewToken")
    await boundary.portal("subscribeMigration")
    await boundary.rpc(
        "logsSubscribe",
        [{"mentions": [PUMP_PROGRAM_ID]}, {"commitment": "confirmed"}],
    )


async def _until_stopped(root: object, clock: Clock) -> None:
    """Subscribe once, then wait until SIGTERM or SIGINT.

    The subscriptions are sent once. The wait only checks for a stop signal, so repeated
    cycles never stack server-side subscriptions.
    """
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    installed: list[signal.Signals] = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError, ValueError):
            continue
        installed.append(sig)
    try:
        await _paper_cycle(root)
        while not stop.is_set():
            await clock.sleep(1.0)
    finally:
        for sig in installed:
            loop.remove_signal_handler(sig)


async def _serve(
    *,
    endpoint: str,
    transport: ReadTransport,
    clock: Clock,
    data_dir: Path,
    budget: RiskBudget,
    limits: EngineLimits,
    once: bool,
    rng_seed: int,
    max_age_s: float,
    max_observations: int,
) -> None:
    rpc = RecordingJsonRpc(endpoint, transport, None, clock)
    root = await build_live_paper_root(
        mode="paper",
        endpoint=endpoint,
        transport=rpc,
        clock=clock,
        rng_seed=rng_seed,
        data_dir=data_dir,
        budget=budget,
        limits=limits,
        max_age_s=max_age_s,
        max_observations=max_observations,
    )
    try:
        if once:
            await _paper_cycle(root)
        else:
            await _until_stopped(root, clock)
    finally:
        root.close()


def serve_once(
    *,
    endpoint: str,
    transport: ReadTransport,
    clock: Clock,
    data_dir: Path,
    budget: RiskBudget,
    limits: EngineLimits,
    once: bool = True,
    rng_seed: int = 0,
    max_age_s: float = _MAX_AGE_S,
    max_observations: int = _MAX_OBSERVATIONS,
) -> int:
    """Build the live-data paper root and run one cycle, or until a stop signal.

    ``once`` is exactly one paper cycle. Without it, the subscriptions are sent once and
    the process waits until SIGTERM or SIGINT. Returns 0.
    """
    asyncio.run(
        _serve(
            endpoint=endpoint,
            transport=transport,
            clock=clock,
            data_dir=data_dir,
            budget=budget,
            limits=limits,
            once=once,
            rng_seed=rng_seed,
            max_age_s=max_age_s,
            max_observations=max_observations,
        )
    )
    return 0
