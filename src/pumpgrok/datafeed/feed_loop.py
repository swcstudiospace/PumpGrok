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
from collections.abc import Callable
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
from pumpgrok.datafeed.transport import RecordingJsonRpc, RecordingWebSocket
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

# How many paper cycles the most recent serve_once call completed.
cycles_run = 0

_CLOSED = object()
_WAIT = object()


class PinnedClock:
    """A clock whose ``now`` stays at the frame arrival ts until ``release``."""

    def __init__(self, inner: Clock) -> None:
        self._inner = inner
        self._pinned: float | None = None

    def pin(self) -> None:
        self._pinned = self._inner.now()

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
    """One frame is pushed, then pump_once reads it. An empty pull is a hard error."""

    def __init__(self) -> None:
        self._pending: deque[object] = deque()

    def push(self, frame: object) -> None:
        self._pending.append(frame)

    async def next_frame(self) -> object:
        if not self._pending:
            raise RuntimeError("pump_once with no pushed frame")
        return self._pending.popleft()

    async def reconnect(self) -> None:
        return None


async def _no_event_consumers(_event: Event) -> None:
    """Curve ticks reach the dataset through the recorder, not an event consumer."""


def _refuse_dead_letter(event: Event) -> None:
    raise RuntimeError(f"record session has no dead-letter sink for {event.kind}")


async def _pull(agen: AsyncIterator[dict[str, object]], clock: Clock, seconds: float) -> object:
    """Next frame, ``_CLOSED`` when the source ends, or ``_WAIT`` on timeout."""
    if seconds <= 0:
        return _WAIT
    try:
        async with clock.timeout(seconds):
            return await anext(agen)
    except StopAsyncIteration:
        return _CLOSED
    except TimeoutError:
        return _WAIT


async def _apply(
    feed: PortalFeed | LogsFeed,
    frames: _PushFrames,
    payload: dict[str, object],
) -> None:
    frames.push(payload)
    await feed.pump_once()


async def _take_portal(
    agen: AsyncIterator[dict[str, object]],
    clock: PinnedClock,
    seconds: float,
    feed: PortalFeed,
    frames: _PushFrames,
    mints: frozenset[str] | None,
) -> object:
    """Pump one ready portal frame. Returns closed, wait, or the handled frame."""
    item = await _pull(agen, clock, seconds)
    if item is _CLOSED or item is _WAIT:
        return item
    if isinstance(item, dict) and _portal_allowed(item, mints):
        await _apply(feed, frames, item)
    return item


async def _take_logs(
    agen: AsyncIterator[dict[str, object]],
    clock: PinnedClock,
    seconds: float,
    feed: LogsFeed,
    frames: _PushFrames,
) -> bool:
    """Pump one ready logs frame. False when the source has ended."""
    item = await _pull(agen, clock, seconds)
    if item is _CLOSED:
        return False
    if item is not _WAIT and isinstance(item, dict):
        await _apply(feed, frames, item)
    return True


async def _pump(
    *,
    clock: PinnedClock,
    deadline: float,
    portal: PortalFeed,
    logs: LogsFeed,
    portal_frames: _PushFrames,
    logs_frames: _PushFrames,
    portal_socket: RecordingWebSocket,
    logs_socket: RecordingWebSocket,
    mints: frozenset[str] | None,
) -> None:
    """Pump portal frames first when they are ready, then logs, until duration or close."""
    portal_agen = aiter(portal_socket)
    logs_agen = aiter(logs_socket)
    portal_open = True
    logs_open = True
    try:
        while clock.monotonic() < deadline and (portal_open or logs_open):
            remaining = deadline - clock.monotonic()
            if remaining <= 0:
                break
            if portal_open:
                slice_s = min(_POLL_S, remaining) if logs_open else remaining
                status = await _take_portal(
                    portal_agen, clock, slice_s, portal, portal_frames, mints
                )
                if status is _CLOSED:
                    portal_open = False
                elif status is not _WAIT:
                    continue
            if logs_open:
                left = deadline - clock.monotonic()
                slice_s = min(_POLL_S, left) if portal_open else left
                logs_open = await _take_logs(logs_agen, clock, slice_s, logs, logs_frames)
    finally:
        await portal_agen.aclose()
        await logs_agen.aclose()


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
    ws_url: str,
) -> Path:
    pinned = PinnedClock(clock)
    recorder = recorder_factory(dataset_dir, clock=pinned)
    recorder.record_frame(
        {"stream": CONFIG_STREAM, "payload": {"watch_capacity": WATCH_CAPACITY}}
    )
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
                portal_socket = RecordingWebSocket(
                    feed_transport.open_websocket(ws_url, stream=PORTAL_STREAM),
                    recorder,
                    stream=PORTAL_STREAM,
                    clock=pinned,
                )
                logs_socket = RecordingWebSocket(
                    feed_transport.open_websocket(_ws_url(endpoint), stream=LOGS_STREAM),
                    recorder,
                    stream=LOGS_STREAM,
                    clock=pinned,
                )
                await _pump(
                    clock=pinned,
                    deadline=deadline,
                    portal=portal,
                    logs=logs,
                    portal_frames=portal_frames,
                    logs_frames=logs_frames,
                    portal_socket=portal_socket,
                    logs_socket=logs_socket,
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
    ws_url: str | None = None,
) -> Path:
    """Record a paper session into ``dataset_dir`` and seal it.

    Runs for ``duration_s`` on ``clock``, or until both frame sources end.
    Returns the sealed directory.
    """
    if isinstance(duration_s, bool) or not isinstance(duration_s, (int, float)) or duration_s <= 0:
        raise ValueError("duration_s must be positive")
    portal_url = ws_url if ws_url is not None else _ws_url(endpoint)
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
            ws_url=portal_url,
        )
    )


async def _paper_cycle(root: object) -> None:
    """One paper cycle: the two portal subscriptions and one logs subscription."""
    global cycles_run
    boundary = root.boundary  # type: ignore[attr-defined]
    await boundary.portal("subscribeNewToken")
    await boundary.portal("subscribeMigration")
    await boundary.rpc(
        "logsSubscribe",
        [{"mentions": [PUMP_PROGRAM_ID]}, {"commitment": "confirmed"}],
    )
    cycles_run += 1


async def _until_stopped(root: object, clock: Clock) -> None:
    """Repeat the paper cycle until SIGTERM or SIGINT, then return."""
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
        while not stop.is_set():
            await _paper_cycle(root)
            if stop.is_set():
                break
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

    ``once`` is exactly one paper cycle. Without it, the same cycle repeats
    until SIGTERM or SIGINT. Returns 0. ``cycles_run`` is the count from this call.
    """
    global cycles_run
    cycles_run = 0
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
