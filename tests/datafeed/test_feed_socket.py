"""Socket-path regressions for the live-data feed loop.

These drive ``feed_loop._pump`` on the real clock with fake socket generators. A poll
timeout really fires while a socket is quiet, so a timeout that finalised the generator
would show here. They also cover arrival fairness between the two sockets, the
programming-error boundary of the frame source, the subscribe-once serve loop, the portal
URL override, and redaction of secret query names.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from pumpgrok.datafeed import feed_loop
from pumpgrok.datafeed.resync import Recovery
from pumpgrok.datafeed.transport import redact_text
from pumpgrok.replay.clock import WallClock

Events = list[tuple[float, dict[str, object]]]


class _Feed:
    """Stands in for a feed: each pumped payload is logged as ``name:n``."""

    def __init__(self, name: str, frames: feed_loop._PushFrames, order: list[str]) -> None:
        self._name = name
        self._frames = frames
        self._order = order

    async def pump_once(self) -> None:
        payload = await self._frames.next_frame()
        assert isinstance(payload, dict)
        self._order.append(f"{self._name}:{payload['n']}")


class _Recorder:
    def record_frame(self, raw: dict[str, Any]) -> None:
        del raw


def _messages(count: int, *, delay: float = 0.0) -> Events:
    return [(delay, {"n": n}) for n in range(1, count + 1)]


async def _socket(events: Events, trace: list[str]) -> AsyncIterator[object]:
    """Yield each message after its delay. ``trace`` records each yield and the finalisation."""
    try:
        for delay, message in events:
            if delay:
                await asyncio.sleep(delay)
            trace.append(f"yield:{message['n']}")
            yield message
    finally:
        trace.append("closed")


async def _run_pump(
    portal_events: Events, logs_events: Events, portal_trace: list[str]
) -> list[str]:
    """Pump both sockets to their end on the real clock and return the feed order."""
    order: list[str] = []
    portal_frames, logs_frames = feed_loop._PushFrames(), feed_loop._PushFrames()
    wall = WallClock()
    await feed_loop._pump(
        clock=feed_loop.PinnedClock(wall),
        arrivals=wall,
        deadline=wall.monotonic() + 10.0,
        portal=cast(Any, _Feed("portal", portal_frames, order)),
        logs=cast(Any, _Feed("logs", logs_frames, order)),
        recorder=cast(Any, _Recorder()),
        portal_frames=portal_frames,
        logs_frames=logs_frames,
        portal_socket=_socket(portal_events, portal_trace),
        logs_socket=_socket(logs_events, []),
        mints=None,
    )
    return order


async def test_quiet_socket_survives_poll_timeouts() -> None:
    """A socket quiet for longer than a 50 ms poll keeps its generator and every frame."""
    portal_trace: list[str] = []
    order = await _run_pump(_messages(2, delay=0.12), [], portal_trace)
    assert portal_trace == ["yield:1", "yield:2", "closed"]
    assert [entry for entry in order if entry.startswith("portal")] == ["portal:1", "portal:2"]


async def test_busy_portal_does_not_starve_logs() -> None:
    """Logs get a turn while portal frames are queued: a logs frame lands before the last one."""
    order = await _run_pump(_messages(40), _messages(1), [])
    assert len(order) == 41
    assert order.index("logs:1") < order.index("portal:40")


async def test_empty_frame_source_is_not_retried_as_a_transport_failure() -> None:
    """An empty pull is a programming error. Recovery must not reconnect or resubscribe on it."""

    async def _unused() -> None:
        raise AssertionError("subscribe must not run")

    recovery = Recovery(
        clock=cast(Any, None),
        supervisor=cast(Any, None),
        frames=feed_loop._PushFrames(),
        gaps=cast(Any, None),
        subscribe=_unused,
        held=lambda: (),
    )
    with pytest.raises(AssertionError, match="no pushed frame"):
        await recovery.receive()


class _Halt(Exception):
    """Ends the serve loop after the scripted number of waits."""


class _HaltingClock:
    def __init__(self, waits: int) -> None:
        self._left = waits

    async def sleep(self, seconds: float) -> None:
        del seconds
        if self._left == 0:
            raise _Halt()
        self._left -= 1


class _Boundary:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def portal(self, method: str) -> object:
        self.sent.append(method)
        return None

    async def rpc(self, method: str, params: list[object]) -> object:
        del params
        self.sent.append(method)
        return None


async def test_serve_loop_subscribes_once_and_does_not_resend() -> None:
    """The serve wait re-checks for a stop signal only; it never re-sends subscriptions."""
    boundary = _Boundary()
    with pytest.raises(_Halt):
        await feed_loop._until_stopped(SimpleNamespace(boundary=boundary), _HaltingClock(3))
    assert boundary.sent == ["subscribeNewToken", "subscribeMigration", "logsSubscribe"]


def test_portal_override_is_named_for_the_portal_socket(tmp_path: Path, monkeypatch: Any) -> None:
    seen: list[dict[str, Any]] = []

    async def _capture(dataset_dir: Path, **kwargs: Any) -> Path:
        seen.append(kwargs)
        return dataset_dir

    monkeypatch.setattr(feed_loop, "_record_session", _capture)
    common: dict[str, Any] = {
        "duration_s": 1,
        "mints": None,
        "clock": WallClock(),
        "transport": None,
        "recorder_factory": feed_loop.recorder_factory,
        "endpoint": "https://rpc.example.invalid",
        "budget": None,
        "limits": None,
    }
    feed_loop.record_session(tmp_path, portal_ws_url="wss://portal.example.invalid/api", **common)
    feed_loop.record_session(tmp_path, **common)
    assert seen[0]["portal_ws_url"] == "wss://portal.example.invalid/api"
    assert seen[1]["portal_ws_url"] == "wss://rpc.example.invalid"


@pytest.mark.parametrize(
    "name",
    ["api-key", "api_key", "apikey", "API_KEY", "key", "token", "access_token", "secret"],
)
def test_secret_query_names_are_redacted(name: str) -> None:
    text = redact_text(f"https://rpc.example.invalid/?{name}=SUPERSECRET123&slot=1")
    assert "SUPERSECRET123" not in text
    assert f"{name}=REDACTED" in text
    assert "slot=1" in text


def test_redaction_does_not_touch_names_that_only_contain_a_secret_word() -> None:
    url = "https://rpc.example.invalid/?monkey=banana"
    assert redact_text(url) == url
