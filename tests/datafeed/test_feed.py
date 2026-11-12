"""Portal and logs feeds: allowlisted reads, bounded recovery, dedup and rate limiting.

Frames and transports are injected. Time is a fixture clock that advances instantly on sleep,
so every backoff and limiter wait is deterministic and no test touches the network.
"""

from __future__ import annotations

import base64
import hashlib
import random
import struct
from dataclasses import dataclass, field
from pathlib import Path

from pumpgrok.datafeed.bridge import ObservationBridge
from pumpgrok.datafeed.logs import PUMP_PROGRAM_ID, LogsFeed
from pumpgrok.datafeed.mintbook import MintBook
from pumpgrok.datafeed.portal import PORTAL_SUBSCRIPTIONS, PortalFeed
from pumpgrok.datafeed.readonly import ReadOnlyBoundary
from pumpgrok.datafeed.resync import DedupWindow, RollingWindowLimiter
from pumpgrok.datafeed.watchset import WatchSet
from pumpgrok.events.models import EventKind
from pumpgrok.events.sources import SourceStatus, SourceSupervisor
from pumpgrok.replay.clock import FixtureClock

START = 1_767_225_600.0
ENDPOINT = "wss://feed.example.test/ws"
_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
ALLOWED_METHODS = {"logsSubscribe", "getTransaction", *PORTAL_SUBSCRIPTIONS}


class StepClock(FixtureClock):
    """Sleep advances virtual time immediately so backoff and limiter waits return at once."""

    async def sleep(self, seconds: float) -> None:
        self.advance_to(self.now() + seconds)


def b58(raw: bytes) -> str:
    number = int.from_bytes(raw, "big")
    out = ""
    while number:
        number, rem = divmod(number, 58)
        out = _ALPHABET[rem] + out
    pad = len(raw) - len(raw.lstrip(b"\0"))
    return "1" * pad + out


def pubkey(index: int) -> tuple[bytes, str]:
    raw = bytes([index]) * 32
    return raw, b58(raw)


MINT_RAW, MINT = pubkey(1)
OTHER_RAW, OTHER = pubkey(2)
USER_RAW, USER = pubkey(3)
TRADE_DISC = hashlib.sha256(b"event:TradeEvent").digest()[:8]


def _u64(value: int) -> bytes:
    return struct.pack("<Q", value)


def _i64(value: int) -> bytes:
    return struct.pack("<q", value)


def encode_trade(*, mint_raw: bytes, sol: int, token: int, vsol: int, vtok: int) -> bytes:
    """Borsh-encode a TradeEvent in the field order pump_events decodes."""
    text = b"swap"
    return b"".join(
        [
            TRADE_DISC,
            mint_raw,
            _u64(sol),
            _u64(token),
            b"\x01",
            USER_RAW,
            _i64(1_767_225_600),
            _u64(vsol),
            _u64(vtok),
            _u64(7),
            _u64(8),
            bytes(32),
            _u64(0),
            _u64(0),
            bytes(32),
            _u64(0),
            _u64(0),
            b"\x00",
            _u64(0),
            _u64(0),
            _u64(0),
            _i64(0),
            struct.pack("<I", len(text)) + text,
            b"\x00",
        ]
    )


def program_data(event: bytes) -> str:
    return "Program data: " + base64.b64encode(event).decode("ascii")


def invoke(program: str) -> str:
    return f"Program {program} invoke [1]"


def success(program: str) -> str:
    return f"Program {program} success"


def logs_frame(signature: str, logs: list[str], *, err: object = None) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "method": "logsNotification",
        "params": {
            "result": {
                "context": {"slot": 1},
                "value": {"signature": signature, "err": err, "logs": logs},
            },
            "subscription": 7,
        },
    }


def trade_logs(event: bytes) -> list[str]:
    return [invoke(PUMP_PROGRAM_ID), program_data(event), success(PUMP_PROGRAM_ID)]


class Transport:
    """Records every outbound frame; answers getTransaction from a scripted table."""

    def __init__(
        self,
        *,
        fail_logs_once: bool = False,
        transactions: dict[str, dict[str, object]] | None = None,
    ) -> None:
        self.sent: list[dict[str, object]] = []
        self._fail_logs_once = fail_logs_once
        self._transactions = transactions or {}

    async def send(self, url: str, frame: dict[str, object]) -> object:
        assert url == ENDPOINT
        self.sent.append(frame)
        method = frame["method"]
        if method == "logsSubscribe" and self._fail_logs_once:
            self._fail_logs_once = False
            raise OSError("socket reset")
        if method == "getTransaction":
            signature = frame["params"][0]  # type: ignore[index]
            return {"jsonrpc": "2.0", "id": frame["id"], "result": self._transactions[signature]}
        return {"jsonrpc": "2.0", "id": frame.get("id"), "result": 1}

    def methods(self) -> list[object]:
        return [frame["method"] for frame in self.sent]


class ScriptedFrames:
    """Pops scripted items; an exception item is raised instead of returned."""

    def __init__(self, script: list[object]) -> None:
        self._script = list(script)
        self.reconnects = 0

    async def next_frame(self) -> object:
        item = self._script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    async def reconnect(self) -> None:
        self.reconnects += 1


@dataclass
class Bus:
    events: list[object] = field(default_factory=list)

    async def publish(self, event: object) -> None:
        self.events.append(event)


@dataclass
class Recorder:
    observations: list[object] = field(default_factory=list)
    gaps: list[object] = field(default_factory=list)

    def record(self, observation: object) -> None:
        self.observations.append(observation)

    def record_gap(self, gap: object) -> None:
        self.gaps.append(gap)


def _kinds(bus: Bus, kind: EventKind) -> list[object]:
    return [event for event in bus.events if getattr(event, "kind", None) is kind]


def _world(tmp_path: Path, *, transport: Transport, watch: WatchSet):
    clock = StepClock(START)
    supervisor = SourceSupervisor(clock, random.Random(0), path=tmp_path / "cursor.db")
    bus = Bus()
    recorder = Recorder()
    bridge = ObservationBridge(bus=bus, recorder=recorder)  # type: ignore[arg-type]
    boundary = ReadOnlyBoundary(endpoint=ENDPOINT, transport=transport)
    limiter = RollingWindowLimiter(clock, limit=30, window_s=10.0)
    return clock, supervisor, bus, recorder, bridge, boundary, limiter


async def test_logs_subscribe_is_one_pump_program_filter_on_the_allowlist(tmp_path: Path) -> None:
    transport = Transport()
    clock, supervisor, _, _, bridge, boundary, limiter = _world(
        tmp_path, transport=transport, watch=WatchSet(max_watched_mints=4)
    )
    feed = LogsFeed(
        boundary=boundary,
        frames=ScriptedFrames([]),
        clock=clock,
        supervisor=supervisor,
        watch=WatchSet(max_watched_mints=4),
        bridge=bridge,
        limiter=limiter,
    )
    await feed.subscribe()
    assert transport.sent == [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": [{"mentions": [PUMP_PROGRAM_ID]}, {"commitment": "confirmed"}],
        }
    ]
    supervisor.close()


async def test_timeout_disconnects_opens_gap_and_reconnect_reseeds_without_a_trade(
    tmp_path: Path,
) -> None:
    transport = Transport()
    watch = WatchSet(max_watched_mints=4)
    assert watch.pin(MINT) is True
    clock, supervisor, _, _, bridge, boundary, limiter = _world(
        tmp_path, transport=transport, watch=watch
    )
    supervisor.note_frame()
    frames = ScriptedFrames([TimeoutError()])
    feed = LogsFeed(
        boundary=boundary,
        frames=frames,
        clock=clock,
        supervisor=supervisor,
        watch=watch,
        bridge=bridge,
        limiter=limiter,
    )
    await feed.subscribe()
    sent_before = len(transport.sent)

    await feed.pump_once()

    assert frames.reconnects == 1
    assert transport.methods()[sent_before:] == ["logsSubscribe"]
    assert supervisor.held_mints == (MINT,)
    assert supervisor.status_at(clock.now()) is SourceStatus.resyncing
    assert feed.gaps.open_gap is False
    assert len(feed.gaps.gaps) == 1
    gap = feed.gaps.gaps[0]
    assert gap.reason == "TimeoutError"
    assert gap.end_ts_utc is not None and gap.end_ts_utc > gap.start_ts_utc
    supervisor.close()


async def test_failed_resubscribe_backs_off_and_retries_until_reseeded(tmp_path: Path) -> None:
    transport = Transport(fail_logs_once=True)
    watch = WatchSet(max_watched_mints=4)
    clock, supervisor, _, _, bridge, boundary, limiter = _world(
        tmp_path, transport=transport, watch=watch
    )
    supervisor.note_frame()
    frames = ScriptedFrames([TimeoutError()])
    feed = LogsFeed(
        boundary=boundary,
        frames=frames,
        clock=clock,
        supervisor=supervisor,
        watch=watch,
        bridge=bridge,
        limiter=limiter,
    )
    await feed.pump_once()
    assert frames.reconnects == 2
    assert transport.methods().count("logsSubscribe") == 2
    assert len(feed.gaps.gaps) == 1
    assert feed.gaps.open_gap is False
    supervisor.close()


async def test_duplicate_notification_publishes_once_and_distinct_events_survive(
    tmp_path: Path,
) -> None:
    transport = Transport()
    watch = WatchSet(max_watched_mints=4)
    assert watch.admit_candidate(MINT) is True
    clock, supervisor, bus, recorder, bridge, boundary, limiter = _world(
        tmp_path, transport=transport, watch=watch
    )
    supervisor.note_frame()
    first = encode_trade(mint_raw=MINT_RAW, sol=1_000, token=500, vsol=30_000, vtok=900_000)
    second = encode_trade(mint_raw=MINT_RAW, sol=2_000, token=700, vsol=31_000, vtok=880_000)
    logs = [invoke(PUMP_PROGRAM_ID), program_data(first), program_data(second)]
    logs.append(success(PUMP_PROGRAM_ID))
    frame = logs_frame("SIG-A", logs)
    frames = ScriptedFrames([frame, frame])
    feed = LogsFeed(
        boundary=boundary,
        frames=frames,
        clock=clock,
        supervisor=supervisor,
        watch=watch,
        bridge=bridge,
        limiter=limiter,
    )
    await feed.pump_once()
    await feed.pump_once()

    trades = _kinds(bus, EventKind.trade)
    assert len(trades) == 2
    assert [t.lamports for t in trades] == [1_000, 2_000]  # type: ignore[attr-defined]
    assert len(_kinds(bus, EventKind.curve_tick)) == 2
    assert len(recorder.observations) == 2
    assert feed.stats.duplicate == 2
    supervisor.close()


async def test_trade_observation_carries_integer_reserves_and_arrival_time(tmp_path: Path) -> None:
    transport = Transport()
    watch = WatchSet(max_watched_mints=4)
    assert watch.admit_candidate(MINT) is True
    clock, supervisor, bus, recorder, bridge, boundary, limiter = _world(
        tmp_path, transport=transport, watch=watch
    )
    supervisor.note_frame()
    event = encode_trade(mint_raw=MINT_RAW, sol=1_000, token=500, vsol=30_000, vtok=900_000)
    feed = LogsFeed(
        boundary=boundary,
        frames=ScriptedFrames([logs_frame("SIG-B", trade_logs(event))]),
        clock=clock,
        supervisor=supervisor,
        watch=watch,
        bridge=bridge,
        limiter=limiter,
    )
    await feed.pump_once()
    (observation,) = recorder.observations
    assert (observation.s_lamports, observation.t_units) == (30_000, 900_000)  # type: ignore[attr-defined]
    assert observation.ts_utc == clock.utc_iso()  # type: ignore[attr-defined]
    assert observation.source == "rpc"  # type: ignore[attr-defined]
    (trade,) = _kinds(bus, EventKind.trade)
    assert trade.token_units == 500  # type: ignore[attr-defined]
    supervisor.close()


async def test_failed_transaction_is_ignored(tmp_path: Path) -> None:
    transport = Transport()
    watch = WatchSet(max_watched_mints=4)
    assert watch.admit_candidate(MINT) is True
    clock, supervisor, bus, _, bridge, boundary, limiter = _world(
        tmp_path, transport=transport, watch=watch
    )
    supervisor.note_frame()
    event = encode_trade(mint_raw=MINT_RAW, sol=1_000, token=500, vsol=30_000, vtok=900_000)
    feed = LogsFeed(
        boundary=boundary,
        frames=ScriptedFrames(
            [logs_frame("SIG-F", trade_logs(event), err={"InstructionError": [0, 1]})]
        ),
        clock=clock,
        supervisor=supervisor,
        watch=watch,
        bridge=bridge,
        limiter=limiter,
    )
    await feed.pump_once()
    assert bus.events == []
    assert feed.stats.failed_tx == 1
    supervisor.close()


async def test_truncated_logs_are_completed_by_one_bounded_get_transaction(tmp_path: Path) -> None:
    event = encode_trade(mint_raw=MINT_RAW, sol=1_000, token=500, vsol=30_000, vtok=900_000)
    full = trade_logs(event)
    transport = Transport(
        transactions={"SIG-T": {"meta": {"err": None, "logMessages": full}}},
    )
    watch = WatchSet(max_watched_mints=4)
    assert watch.admit_candidate(MINT) is True
    clock, supervisor, bus, _, bridge, boundary, limiter = _world(
        tmp_path, transport=transport, watch=watch
    )
    supervisor.note_frame()
    truncated = [invoke(PUMP_PROGRAM_ID), "Log truncated"]
    feed = LogsFeed(
        boundary=boundary,
        frames=ScriptedFrames([logs_frame("SIG-T", truncated)]),
        clock=clock,
        supervisor=supervisor,
        watch=watch,
        bridge=bridge,
        limiter=limiter,
    )
    await feed.pump_once()
    assert transport.methods().count("getTransaction") == 1
    assert len(_kinds(bus, EventKind.trade)) == 1
    supervisor.close()


async def test_unknown_discriminator_is_counted_and_never_guessed(tmp_path: Path) -> None:
    transport = Transport()
    watch = WatchSet(max_watched_mints=4)
    assert watch.admit_candidate(MINT) is True
    clock, supervisor, bus, _, bridge, boundary, limiter = _world(
        tmp_path, transport=transport, watch=watch
    )
    supervisor.note_frame()
    garbage = bytes(8) + MINT_RAW
    logs = [invoke(PUMP_PROGRAM_ID), program_data(garbage), success(PUMP_PROGRAM_ID)]
    feed = LogsFeed(
        boundary=boundary,
        frames=ScriptedFrames([logs_frame("SIG-U", logs)]),
        clock=clock,
        supervisor=supervisor,
        watch=watch,
        bridge=bridge,
        limiter=limiter,
    )
    await feed.pump_once()
    assert bus.events == []
    assert feed.stats.undecodable == 1
    supervisor.close()


async def test_program_data_from_another_program_is_not_attributed_to_pump(
    tmp_path: Path,
) -> None:
    transport = Transport()
    watch = WatchSet(max_watched_mints=4)
    assert watch.admit_candidate(MINT) is True
    clock, supervisor, bus, _, bridge, boundary, limiter = _world(
        tmp_path, transport=transport, watch=watch
    )
    supervisor.note_frame()
    event = encode_trade(mint_raw=MINT_RAW, sol=1_000, token=500, vsol=30_000, vtok=900_000)
    token_program = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
    logs = [invoke(token_program), program_data(event), success(token_program)]
    feed = LogsFeed(
        boundary=boundary,
        frames=ScriptedFrames([logs_frame("SIG-X", logs)]),
        clock=clock,
        supervisor=supervisor,
        watch=watch,
        bridge=bridge,
        limiter=limiter,
    )
    await feed.pump_once()
    assert bus.events == []
    supervisor.close()


async def test_trade_for_unwatched_mint_is_counted_not_published(tmp_path: Path) -> None:
    transport = Transport()
    watch = WatchSet(max_watched_mints=4)
    clock, supervisor, bus, recorder, bridge, boundary, limiter = _world(
        tmp_path, transport=transport, watch=watch
    )
    supervisor.note_frame()
    event = encode_trade(mint_raw=OTHER_RAW, sol=1_000, token=500, vsol=30_000, vtok=900_000)
    feed = LogsFeed(
        boundary=boundary,
        frames=ScriptedFrames([logs_frame("SIG-W", trade_logs(event))]),
        clock=clock,
        supervisor=supervisor,
        watch=watch,
        bridge=bridge,
        limiter=limiter,
    )
    await feed.pump_once()
    assert bus.events == []
    assert recorder.observations == []
    assert feed.stats.unwatched == 1
    supervisor.close()


async def test_malformed_frame_is_counted_and_does_not_end_the_feed(tmp_path: Path) -> None:
    transport = Transport()
    watch = WatchSet(max_watched_mints=4)
    clock, supervisor, bus, _, bridge, boundary, limiter = _world(
        tmp_path, transport=transport, watch=watch
    )
    supervisor.note_frame()
    feed = LogsFeed(
        boundary=boundary,
        frames=ScriptedFrames([{"method": "logsNotification"}, "not-a-frame"]),
        clock=clock,
        supervisor=supervisor,
        watch=watch,
        bridge=bridge,
        limiter=limiter,
    )
    await feed.pump_once()
    await feed.pump_once()
    assert bus.events == []
    assert feed.stats.malformed == 2
    supervisor.close()


async def test_rolling_window_admits_thirty_per_ten_seconds_on_injected_clock() -> None:
    clock = StepClock(START)
    limiter = RollingWindowLimiter(clock, limit=30, window_s=10.0)
    times: list[float] = []
    for _ in range(60):
        await limiter.acquire()
        times.append(clock.now())
    assert times[:30] == [START] * 30
    assert times[30] == START + 10.0
    for index in range(len(times) - 30):
        assert times[index + 30] - times[index] >= 10.0


async def test_rolling_window_boundary_is_half_open_at_ten_seconds() -> None:
    clock = StepClock(START)
    limiter = RollingWindowLimiter(clock, limit=2, window_s=10.0)
    await limiter.acquire()
    await limiter.acquire()
    clock.advance_to(START + 9.5)
    await limiter.acquire()
    assert clock.now() == START + 10.0


def test_dedup_window_is_bounded_and_forgets_the_oldest_key() -> None:
    window = DedupWindow(capacity=2)
    assert window.admit(("a", 0)) is True
    assert window.admit(("b", 0)) is True
    assert window.admit(("a", 0)) is False
    assert window.admit(("c", 0)) is True
    assert len(window) == 2
    assert window.admit(("a", 0)) is True


# ---------------------------------------------------------------- Portal


def _portal(tmp_path: Path, *, transport: Transport, watch: WatchSet, frames: ScriptedFrames):
    clock, supervisor, bus, recorder, bridge, boundary, limiter = _world(
        tmp_path, transport=transport, watch=watch
    )
    supervisor.note_frame()
    book = MintBook(watch=watch)
    feed = PortalFeed(
        boundary=boundary,
        frames=frames,
        clock=clock,
        supervisor=supervisor,
        mintbook=book,
        bridge=bridge,
        limiter=limiter,
    )
    return feed, clock, supervisor, bus, book


async def test_portal_subscribes_only_to_allowlisted_creation_and_migration(tmp_path: Path) -> None:
    transport = Transport()
    feed, _, supervisor, _, _ = _portal(
        tmp_path,
        transport=transport,
        watch=WatchSet(max_watched_mints=4),
        frames=ScriptedFrames([]),
    )
    await feed.subscribe()
    assert transport.sent == [{"method": "subscribeNewToken"}, {"method": "subscribeMigration"}]
    assert set(transport.methods()) <= ALLOWED_METHODS
    supervisor.close()


async def test_portal_creation_admits_watch_and_publishes_token_created(tmp_path: Path) -> None:
    transport = Transport()
    watch = WatchSet(max_watched_mints=4)
    create = {
        "txType": "create",
        "mint": MINT,
        "name": "Coin",
        "symbol": "CN",
        "traderPublicKey": USER,
        "signature": "SIG-C",
        "bondingCurveKey": OTHER,
    }
    feed, clock, supervisor, bus, book = _portal(
        tmp_path, transport=transport, watch=watch, frames=ScriptedFrames([create])
    )
    await feed.pump_once()
    record = book.record(MINT)
    assert record is not None and record.stage == "created"
    (event,) = _kinds(bus, EventKind.token_created)
    assert event.entity_id == MINT  # type: ignore[attr-defined]
    assert event.occurred_at == clock.utc_iso()  # type: ignore[attr-defined]
    assert event.payload["signature"] == "SIG-C"  # type: ignore[attr-defined]
    supervisor.close()


async def test_portal_overflowing_creation_is_counted_and_not_published(tmp_path: Path) -> None:
    transport = Transport()
    watch = WatchSet(max_watched_mints=1)
    assert watch.admit_candidate(OTHER) is True
    create = {"txType": "create", "mint": MINT, "name": "C", "symbol": "C", "signature": "S"}
    feed, _, supervisor, bus, book = _portal(
        tmp_path, transport=transport, watch=watch, frames=ScriptedFrames([create])
    )
    await feed.pump_once()
    assert book.record(MINT) is None
    assert _kinds(bus, EventKind.token_created) == []
    assert watch.overflow == 1
    supervisor.close()


async def test_portal_migration_publishes_only_for_watched_mints(tmp_path: Path) -> None:
    transport = Transport()
    watch = WatchSet(max_watched_mints=4)
    assert watch.admit_candidate(MINT) is True
    migrate_known = {"txType": "migrate", "mint": MINT, "signature": "SIG-M", "pool": "P"}
    migrate_unknown = {"txType": "migrate", "mint": OTHER, "signature": "SIG-N", "pool": "P"}
    feed, _, supervisor, bus, book = _portal(
        tmp_path,
        transport=transport,
        watch=watch,
        frames=ScriptedFrames([migrate_known, migrate_unknown]),
    )
    await feed.pump_once()
    await feed.pump_once()
    (event,) = _kinds(bus, EventKind.migration)
    assert event.entity_id == MINT  # type: ignore[attr-defined]
    record = book.record(MINT)
    assert record is not None and record.stage == "migrated"
    assert feed.stats.unwatched == 1
    supervisor.close()


async def test_portal_unknown_transaction_type_is_counted_not_guessed(tmp_path: Path) -> None:
    transport = Transport()
    watch = WatchSet(max_watched_mints=4)
    feed, _, supervisor, bus, _ = _portal(
        tmp_path,
        transport=transport,
        watch=watch,
        frames=ScriptedFrames([{"txType": "buy", "mint": MINT}, {"mint": MINT}]),
    )
    await feed.pump_once()
    await feed.pump_once()
    assert bus.events == []
    assert feed.stats.malformed == 2
    supervisor.close()


async def test_portal_timeout_disconnects_and_reseeds_subscriptions(tmp_path: Path) -> None:
    transport = Transport()
    watch = WatchSet(max_watched_mints=4)
    frames = ScriptedFrames([TimeoutError()])
    feed, clock, supervisor, _, _ = _portal(
        tmp_path, transport=transport, watch=watch, frames=frames
    )
    await feed.subscribe()
    sent_before = len(transport.sent)
    await feed.pump_once()
    assert frames.reconnects == 1
    assert transport.sent[sent_before:] == [
        {"method": "subscribeNewToken"},
        {"method": "subscribeMigration"},
    ]
    assert len(feed.gaps.gaps) == 1
    assert feed.gaps.open_gap is False
    supervisor.close()
