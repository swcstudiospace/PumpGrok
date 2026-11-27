"""Replay dataset maintenance: ``replay trim``, ``replay rebuild-ticks`` and ``replay import``.

Every function here is deterministic and network-free. No transport, RPC or LLM client is
imported, and a rebuild answers every read from the recorded feed alone. ``root`` is the
operator's ``var`` directory. Datasets live under ``<root>/datasets/<name>``; an imported ledger
lives under ``<root>/replay/<name>``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from collections import deque
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from pumpgrok.core.errors import PumpgrokError
from pumpgrok.datafeed.bridge import build_observation_bridge
from pumpgrok.datafeed.logs import LogsFeed
from pumpgrok.datafeed.mintbook import MintBook
from pumpgrok.datafeed.portal import PortalFeed
from pumpgrok.datafeed.readonly import ReadOnlyBoundary
from pumpgrok.datafeed.resync import RollingWindowLimiter
from pumpgrok.datafeed.watchset import WatchSet
from pumpgrok.events.models import Event
from pumpgrok.events.sources import SourceSupervisor
from pumpgrok.ledger.store import LedgerInconsistent, LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.fixtures import (
    EVENTS_NAME,
    MANIFEST_NAME,
    CorruptFixture,
    FixtureManifest,
    load_dataset,
)
from pumpgrok.replay.live_recorder import (
    CONFIG_STREAM,
    FEED_NAME,
    GAPS_NAME,
    LOGS_STREAM,
    PORTAL_STREAM,
    TRANSACTION_STREAM,
    LiveRecorder,
    seal_directory,
)
from pumpgrok.replay.rng import make_rng

__all__ = [
    "TRIM_KEEP_FRACTION",
    "MaintenanceRefused",
    "import_dataset",
    "rebuild_ticks",
    "trim",
]

# Events of mints without an order are kept with this probability, drawn from the seeded RNG.
TRIM_KEEP_FRACTION = 0.05
IMPORTED_LEDGER_NAME = "imported-ledger.sqlite"
IMPORTED_DIGEST_NAME = IMPORTED_LEDGER_NAME + ".sha256"
# The endpoint a replayed feed is bound to. Replay never opens it: every read is answered from the
# recorded feed, and a read the recording does not hold refuses the rebuild.
_REPLAY_ENDPOINT = "wss://pumpportal.fun/api/data"
_RATE_WINDOW_S = 10.0


class MaintenanceRefused(PumpgrokError):
    """A maintenance request this module refuses, before anything is written.

    ``fields["kind"]`` selects the CLI exit code: ``usage`` (bad name, missing input, existing
    target, nothing to keep) exits 1; ``ledger`` (a ledger that fails verification or holds a row
    this desk did not record) exits 2.
    """

    code = "maintenance_refused"


def _plain_name(name: str) -> str:
    try:
        FixtureManifest._plain_dataset_name(name)
    except ValueError:
        raise MaintenanceRefused("dataset name is not a plain name", kind="usage") from None
    return name


def _verified_bytes(dataset_dir: Path, manifest: FixtureManifest, name: str) -> bytes:
    """Read one listed file again and check it against its manifest digest."""
    data = (dataset_dir / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest.sha256[name]:
        raise CorruptFixture("sha256 does not match manifest", file=name)
    return data


def _write_new(path: Path, data: bytes) -> None:
    """Create a file that must not exist, and make its bytes durable."""
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _select_kept(
    events_bytes: bytes,
    events: tuple[dict[str, Any], ...],
    orders: frozenset[str],
    seed: int,
    max_events: int,
) -> list[tuple[bytes, dict[str, Any]]]:
    """Keep order-mint events and a seeded fraction of the rest, then the tail."""
    lines = events_bytes.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    if len(lines) != len(events):
        raise CorruptFixture("event line count does not match the loaded events", file=EVENTS_NAME)
    rng = make_rng(seed)
    kept: list[tuple[bytes, dict[str, Any]]] = []
    for raw, event in zip(lines, events, strict=True):
        if event.get("mint") in orders or rng.random() < TRIM_KEEP_FRACTION:
            kept.append((raw, event))
    kept = kept[-max_events:]
    if not kept:
        raise MaintenanceRefused("trim keeps no events", kind="usage")
    return kept


def trim(
    name: str,
    *,
    root: Path,
    max_events: int,
    seed: int,
    mints_with_orders: Callable[[Path], frozenset[str]],
) -> Path:
    """Write ``<name>-trimmed``: every event of a mint with an order, a seeded 5 percent of the
    rest, then the last ``max_events`` of those kept events in file order.

    ``mints_with_orders`` names the mints that hold an order row when the source dataset is
    replayed. The RNG is drawn only for events of mints without an order, in file order, so one
    seed gives one output. ``gaps.jsonl`` is copied unchanged when the source lists it. No gap is
    inserted and ``feed.jsonl`` is not carried over.
    """
    if type(max_events) is not int or max_events <= 0:
        raise MaintenanceRefused("max-events must be a positive integer", kind="usage")
    _plain_name(name)
    source = root / "datasets" / name
    if not source.is_dir():
        raise MaintenanceRefused(f"dataset not found: {name}", kind="usage")
    dataset = load_dataset(source)
    manifest = dataset.manifest
    events_bytes = _verified_bytes(source, manifest, EVENTS_NAME)
    kept = _select_kept(events_bytes, dataset.events, mints_with_orders(source), seed, max_events)

    target = root / "datasets" / f"{name}-trimmed"
    if target.exists():
        raise MaintenanceRefused(f"target exists: {target.name}", kind="usage")
    target.mkdir(parents=True)
    try:
        _write_new(target / EVENTS_NAME, b"".join(raw + b"\n" for raw, _ in kept))
        if GAPS_NAME in manifest.sha256:
            _write_new(target / GAPS_NAME, _verified_bytes(source, manifest, GAPS_NAME))
        sources = {str(event["source"]): str(event["source"]) for _, event in kept}
        seal_directory(
            target,
            recorded_from_utc=str(kept[0][1]["ts_utc"]),
            recorded_to_utc=str(kept[-1][1]["ts_utc"]),
            sources=sources,
            seed_hint=seed,
            notes=(
                f"Trimmed from {name}: keep every event of a mint with an order, "
                f"a seeded {TRIM_KEEP_FRACTION:.0%} of the rest, last {max_events} kept"
            ),
        )
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return target


@dataclass(frozen=True)
class _Frame:
    ts: float
    stream: str
    payload: dict[str, Any]
    line: int


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-finite JSON constant {name}")


def _read_manifest(dataset_dir: Path) -> FixtureManifest:
    """Read and shape-check manifest.json without verifying any listed data file."""
    try:
        raw = json.loads(
            (dataset_dir / MANIFEST_NAME).read_text(encoding="utf-8"),
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeDecodeError, ValueError):
        raise CorruptFixture("manifest is missing or not valid JSON", file=MANIFEST_NAME) from None
    try:
        return FixtureManifest.model_validate(raw)
    except ValidationError:
        raise CorruptFixture("manifest is invalid", file=MANIFEST_NAME) from None


def _parse_feed(data: bytes) -> list[_Frame]:
    """Each line is one frame ``{"ts", "stream", "payload"}``. Any other shape is refused."""
    lines = data.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    frames: list[_Frame] = []
    for number, raw in enumerate(lines, 1):
        try:
            value = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
        except (UnicodeDecodeError, ValueError):
            raise CorruptFixture("line is not valid JSON", file=FEED_NAME, line=number) from None
        if not isinstance(value, dict) or set(value) != {"ts", "stream", "payload"}:
            raise CorruptFixture(
                "frame must hold ts, stream and payload", file=FEED_NAME, line=number
            )
        ts, stream, payload = value["ts"], value["stream"], value["payload"]
        if isinstance(ts, bool) or not isinstance(ts, (int, float)):
            raise CorruptFixture("frame ts is not a number", file=FEED_NAME, line=number)
        if not isinstance(stream, str) or not isinstance(payload, dict):
            raise CorruptFixture(
                "frame stream or payload has the wrong type", file=FEED_NAME, line=number
            )
        frames.append(_Frame(ts=float(ts), stream=stream, payload=payload, line=number))
    return frames


def _plan(frames: list[_Frame]) -> tuple[int, dict[str, deque[dict[str, Any]]], list[_Frame]]:
    """Split the feed into its watch capacity, its recorded getTransaction responses and the
    portal and logs frames to replay, in ``(ts, line)`` order."""
    configs = [frame for frame in frames if frame.stream == CONFIG_STREAM]
    if len(configs) != 1:
        raise CorruptFixture("feed must hold exactly one config frame", file=FEED_NAME)
    config = configs[0]
    capacity = config.payload.get("watch_capacity")
    if set(config.payload) != {"watch_capacity"} or type(capacity) is not int or capacity <= 0:
        raise CorruptFixture(
            "config frame must hold a positive watch_capacity", file=FEED_NAME, line=config.line
        )
    responses: dict[str, deque[dict[str, Any]]] = {}
    replayed: list[_Frame] = []
    for frame in sorted(frames, key=lambda item: (item.ts, item.line)):
        if frame.stream == TRANSACTION_STREAM:
            signature = frame.payload.get("signature")
            response = frame.payload.get("response")
            if (
                set(frame.payload) != {"signature", "response"}
                or not isinstance(signature, str)
                or not isinstance(response, dict)
            ):
                raise CorruptFixture(
                    "transaction frame must hold signature and response",
                    file=FEED_NAME,
                    line=frame.line,
                )
            responses.setdefault(signature, deque()).append(response)
        elif frame.stream in (PORTAL_STREAM, LOGS_STREAM):
            replayed.append(frame)
        elif frame.stream != CONFIG_STREAM:
            raise CorruptFixture("feed holds an unknown stream", file=FEED_NAME, line=frame.line)
    return capacity, responses, replayed


class _StreamFrames:
    """Frame source of one replayed feed. The frame is pushed just before its pump runs."""

    def __init__(self) -> None:
        self._pending: deque[object] = deque()

    def push(self, frame: object) -> None:
        self._pending.append(frame)

    async def next_frame(self) -> object:
        return self._pending.popleft()

    async def reconnect(self) -> None:
        raise CorruptFixture("a recorded feed cannot reconnect during rebuild", file=FEED_NAME)


class _RecordedReads:
    """The read transport of a rebuild. It answers only from recorded getTransaction responses.

    A read the recording does not hold is noted and refused. The feed then records a gap
    instead of raising, so the rebuild checks ``unrecorded`` after every frame.
    """

    def __init__(self, responses: dict[str, deque[dict[str, Any]]]) -> None:
        self._responses = responses
        self.unrecorded: list[str] = []

    async def send(self, url: str, frame: dict[str, object]) -> object:
        method = frame.get("method")
        params = frame.get("params")
        signature = params[0] if isinstance(params, list) and params else None
        queue: deque[dict[str, Any]] | None = None
        if method == "getTransaction" and isinstance(signature, str):
            queue = self._responses.get(signature)
        if not queue:
            self.unrecorded.append(str(method))
            raise RuntimeError("no recorded response for this read")
        return queue.popleft()


async def _no_event_consumers(_event: Event) -> None:
    """A rebuild publishes no events: curve ticks reach the recorder through the bridge."""


def _refuse_dead_letter(_event: Event) -> None:
    raise CorruptFixture("a rebuilt event could not be handed to its consumer", file=FEED_NAME)


async def _replay(
    frames: list[_Frame],
    *,
    capacity: int,
    responses: dict[str, deque[dict[str, Any]]],
    feed: bytes,
    gaps: bytes | None,
    target: Path,
    scratch: Path,
) -> None:
    """Run the recorded portal and logs frames through the live feed code, clocked at each frame.

    Every observation is stamped with its frame's ts, because the clock is set to that ts before
    the frame is pumped. The rebuilt dataset gets the recorded feed and gaps bytes unchanged, so
    it is rebuildable in turn.
    """
    clock = FixtureClock(0.0)
    recorder = LiveRecorder(target, clock=clock)
    bridge = build_observation_bridge(
        clock=clock,
        handler=_no_event_consumers,
        dlq=_refuse_dead_letter,
        recorder=recorder,
    )
    reads = _RecordedReads(responses)
    boundary = ReadOnlyBoundary(endpoint=_REPLAY_ENDPOINT, transport=reads)
    # Replay makes no paced reads, so the limiter never waits: a wait would move the clock.
    limiter = RollingWindowLimiter(clock, limit=len(frames) + 1, window_s=_RATE_WINDOW_S)
    watch = WatchSet(max_watched_mints=capacity)
    mintbook = MintBook(watch=watch)
    portal_frames, logs_frames = _StreamFrames(), _StreamFrames()
    with closing(SourceSupervisor(clock, make_rng(), path=scratch / "cursor.sqlite")) as supervisor:
        portal = PortalFeed(
            boundary=boundary,
            frames=portal_frames,
            clock=clock,
            supervisor=supervisor,
            mintbook=mintbook,
            bridge=bridge,
            limiter=limiter,
        )
        logs = LogsFeed(
            boundary=boundary,
            frames=logs_frames,
            clock=clock,
            supervisor=supervisor,
            watch=watch,
            bridge=bridge,
            limiter=limiter,
        )
        for frame in frames:
            clock.advance_to(frame.ts)
            if frame.stream == PORTAL_STREAM:
                portal_frames.push(frame.payload)
                await portal.pump_once()
            else:
                logs_frames.push(frame.payload)
                await logs.pump_once()
            if reads.unrecorded:
                raise CorruptFixture(
                    "a truncated notification needs a read the recording does not hold",
                    file=FEED_NAME,
                    method=reads.unrecorded[0],
                )
    leftover = sorted(signature for signature, queue in responses.items() if queue)
    if leftover:
        raise CorruptFixture("a recorded transaction response was never requested", file=FEED_NAME)
    if not await asyncio.to_thread((target / EVENTS_NAME).is_file):
        raise CorruptFixture("the feed yields no curve observations", file=FEED_NAME)
    _write_new(target / FEED_NAME, feed)
    if gaps is not None:
        _write_new(target / GAPS_NAME, gaps)
    try:
        recorder.seal()
    except ValueError:
        raise CorruptFixture("the feed yields no curve observations", file=FEED_NAME) from None


def rebuild_ticks(name: str, *, root: Path) -> Path:
    """Write ``<name>-rebuilt``: the curve ticks of ``<name>``, derived from its raw feed alone.

    ``feed.jsonl`` is the only input. The derived ``events.jsonl`` is never read, so deleting or
    corrupting it leaves the output unchanged (owner decision 3). The feed is replayed through
    the live portal and logs feed code, with the clock at each frame's ts and the watch capacity
    taken from the recorded config frame. A getTransaction read is answered only from a recorded
    response; one the recording does not hold refuses the rebuild.
    """
    _plain_name(name)
    source = root / "datasets" / name
    if not source.is_dir():
        raise MaintenanceRefused(f"dataset not found: {name}", kind="usage")
    manifest = _read_manifest(source)
    if FEED_NAME not in manifest.sha256:
        raise CorruptFixture("dataset lists no raw feed stream", file=FEED_NAME)
    feed = _verified_bytes(source, manifest, FEED_NAME)
    gaps = _verified_bytes(source, manifest, GAPS_NAME) if GAPS_NAME in manifest.sha256 else None
    capacity, responses, frames = _plan(_parse_feed(feed))
    target = root / "datasets" / f"{name}-rebuilt"
    try:
        target.mkdir()
    except FileExistsError:
        raise MaintenanceRefused(f"target exists: {target.name}", kind="usage") from None
    try:
        with tempfile.TemporaryDirectory() as scratch:
            asyncio.run(
                _replay(
                    frames,
                    capacity=capacity,
                    responses=responses,
                    feed=feed,
                    gaps=gaps,
                    target=target,
                    scratch=Path(scratch),
                )
            )
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return target


def _verify_paper_ledger(path: Path) -> None:
    """Refuse unless the ledger verifies from genesis and every row was recorded by paper."""
    try:
        store = LedgerStore(str(path))
    except sqlite3.Error:
        raise MaintenanceRefused(
            "ledger is not a readable sqlite database", kind="ledger"
        ) from None
    try:
        store.verify()
        rows = store.read(limit=None)
    except (LedgerInconsistent, sqlite3.Error):
        raise MaintenanceRefused("ledger does not verify from genesis", kind="ledger") from None
    finally:
        store.close()
    if not rows:
        raise MaintenanceRefused("ledger holds no rows", kind="ledger")
    if any(row["source"] != "paper" for row in rows):
        raise MaintenanceRefused("ledger holds a row whose source is not paper", kind="ledger")


def _backup_copy(source: Path, destination: Path) -> None:
    """Copy ``source`` to a new file at ``destination`` with the sqlite backup API.

    The backup reads through the WAL, so rows committed to the ``-wal`` sidecar and not yet
    checkpointed are included. A byte copy of the main file would miss them and attest a partial
    ledger. The source is opened read-only and never written.
    """
    try:
        with (
            closing(sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)) as src,
            closing(sqlite3.connect(str(destination))) as dst,
        ):
            src.backup(dst)
    except sqlite3.Error:
        raise MaintenanceRefused(
            "ledger is not a readable sqlite database", kind="ledger"
        ) from None


def import_dataset(ledger: Path, *, name: str, root: Path) -> Path:
    """Copy a ledger this desk recorded to ``<root>/replay/<name>/imported-ledger.sqlite``.

    Accepted only when the ledger verifies from genesis and every row's source is ``paper``
    (owner decision 1, 2026-11-15). The ledger is copied with the sqlite backup API into a
    scratch file beside the target, that copy is verified, and it is renamed into place. Its
    sha256 is written beside it in ``sha256sum`` form. Nothing is converted. An existing target
    is refused before anything is written into it.
    """
    _plain_name(name)
    if not ledger.is_file():
        raise MaintenanceRefused("ledger file not found", kind="usage")
    target = root / "replay" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix=f".{name}-import-") as scratch:
        copy = Path(scratch) / IMPORTED_LEDGER_NAME
        _backup_copy(ledger, copy)
        _verify_paper_ledger(copy)
        with copy.open("rb") as stream:
            os.fsync(stream.fileno())
        digest = hashlib.sha256(copy.read_bytes()).hexdigest()
        try:
            target.mkdir()
        except FileExistsError:
            raise MaintenanceRefused(f"target exists: {name}", kind="usage") from None
        try:
            os.replace(copy, target / IMPORTED_LEDGER_NAME)
            digest_line = f"{digest}  {IMPORTED_LEDGER_NAME}\n"
            _write_new(target / IMPORTED_DIGEST_NAME, digest_line.encode("utf-8"))
        except BaseException:
            shutil.rmtree(target, ignore_errors=True)
            raise
    return target
