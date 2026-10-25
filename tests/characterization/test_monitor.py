"""Characterization: fail-closed launch filter (STRUCT-003).

Pins ``engine/monitor.py`` against ``vendor/grokbot-pumpfun/tests/test_filter.py``
(vendor oracle, kept byte-identical per R53).

Adaptations from the oracle (deliberate, R45/R46: no trade subscription):

- ``test_buyers_boundary`` (vendor ``:69-73``) asserted ``few_buyers`` on a
  low count. The port keeps that case for an *observed* low count, and adds
  ``test_missing_buyer_evidence_fails_closed``: ``unique_buyers=None`` (no
  evidence) yields the new ASCII code ``data_unavailable``.
- ``test_token_emitted_once_it_matures`` (``:137-156``),
  ``test_same_wallet_does_not_inflate_buyer_count`` (``:158-168``), and
  ``test_sweep_emits_matured_token`` (``:199-207``) fed ``buy`` events into
  ``handle_event``. The port ignores non-create payloads, so buyer evidence
  is set on the buffered token directly (standing in for the Phase 4
  pipeline path, which reads it outside the socket) or asserted absent.
- ``test_stream_yields_matured_token`` (``:285-304``) asserted
  ``subscribeTokenTrade``/``unsubscribeTokenTrade`` traffic. The port sends
  ``subscribeNewToken`` only; the test asserts exactly that.
- ``test_stream_reconnects_after_drop`` (``:307-327``) and
  ``test_stream_survives_broken_json`` (``:329-343``) are kept in shape but
  no matured token ever arrives over the wire: without buyer evidence every
  buffered token ends in ``data_unavailable``.
- Time is explicit everywhere: ``parse_create_event``, ``handle_event``,
  ``sweep``, and ``passes_filter`` take ``now`` instead of reading the
  wall clock.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

import pytest

import pumpgrok.engine.monitor as monitor_module
from pumpgrok.config.settings import DataSettings, FilterSettings
from pumpgrok.engine.models import Token
from pumpgrok.engine.monitor import (
    CURVE_COMPLETION_LAMPORTS,
    LaunchMonitor,
    SeenSet,
    parse_create_event,
    passes_filter,
)
from pumpgrok.replay.clock import FixtureClock

NOW = 1_700_000_000.0


def make_monitor(skips: list, clock: Any = None) -> LaunchMonitor:
    return LaunchMonitor(
        DataSettings(),
        FilterSettings(min_unique_buyers=3, min_age_seconds=120.0),
        FixtureClock() if clock is None else clock,
        on_skip=lambda t, r: skips.append((t.mint, r)),
    )


class ManualClock:
    """Controllable now with real sleeps: stream tests must not hang the
    virtual clock on backoff sleeps."""

    def __init__(self, now: float) -> None:
        self._now = now

    def now(self) -> float:
        return self._now

    def monotonic(self) -> float:
        return self._now

    def utc_iso(self) -> str:
        return str(self._now)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    def timeout(self, seconds: float) -> Any:
        return asyncio.timeout(seconds)


@pytest.fixture
def cfg() -> FilterSettings:
    return FilterSettings(
        min_unique_buyers=5,
        max_curve_progress=0.40,
        require_metadata=True,
        min_age_seconds=120.0,
    )


def make_token(**overrides: Any) -> Token:
    base: dict[str, Any] = {
        "mint": "Mint111",
        "name": "Doge Killer",
        "image_uri": "https://img/1.png",
        "created_timestamp": NOW - 300,
        "unique_buyers": 10,
        "curve_progress": 0.15,
    }
    base.update(overrides)
    return Token(**base)


def test_healthy_token_passes(cfg: FilterSettings) -> None:
    ok, reason = passes_filter(make_token(), cfg, NOW)
    assert ok and reason == "ok"


def test_missing_metadata_rejected(cfg: FilterSettings) -> None:
    ok, reason = passes_filter(make_token(image_uri=None), cfg, NOW)
    assert not ok and reason == "no_metadata"


def test_metadata_ignored_when_not_required(cfg: FilterSettings) -> None:
    open_cfg = cfg.model_copy(update={"require_metadata": False})
    ok, _ = passes_filter(make_token(image_uri=None), open_cfg, NOW)
    assert ok


def test_too_young_rejected(cfg: FilterSettings) -> None:
    ok, reason = passes_filter(make_token(created_timestamp=NOW - 60), cfg, NOW)
    assert not ok and reason == "too_young"


def test_age_boundary_is_inclusive(cfg: FilterSettings) -> None:
    """Exactly 120 seconds old already passes; 119.9 does not."""
    ok, _ = passes_filter(make_token(created_timestamp=NOW - 120.0), cfg, NOW)
    assert ok
    ok, reason = passes_filter(make_token(created_timestamp=NOW - 119.9), cfg, NOW)
    assert not ok and reason == "too_young"


def test_missing_buyer_evidence_fails_closed(cfg: FilterSettings) -> None:
    """No trade evidence is not zero buyers: it is data_unavailable."""
    ok, reason = passes_filter(make_token(unique_buyers=None), cfg, NOW)
    assert not ok and reason == "data_unavailable"


def test_observed_few_buyers_still_few_buyers(cfg: FilterSettings) -> None:
    """An explicitly observed low count keeps the vendor code."""
    ok, reason = passes_filter(make_token(unique_buyers=4), cfg, NOW)
    assert not ok and reason == "few_buyers"
    ok, _ = passes_filter(make_token(unique_buyers=5), cfg, NOW)
    assert ok


def test_curve_boundary(cfg: FilterSettings) -> None:
    ok, _ = passes_filter(make_token(curve_progress=0.399), cfg, NOW)
    assert ok
    ok, reason = passes_filter(make_token(curve_progress=0.40), cfg, NOW)
    assert not ok and reason == "curve_too_full"


def test_terminal_reasons_win_over_temporary(cfg: FilterSettings) -> None:
    """Order matters: a hopeless token must not sit in the buffer."""
    ok, reason = passes_filter(
        make_token(image_uri=None, created_timestamp=NOW - 10, curve_progress=0.9),
        cfg,
        NOW,
    )
    assert not ok and reason == "no_metadata"


def test_data_unavailable_is_terminal_not_buffered(cfg: FilterSettings) -> None:
    """Without a trade stream a data_unavailable token can never gain
    evidence, so _promote must not buffer it."""
    skips: list = []
    mon = make_monitor(skips)
    mon.handle_event(
        {
            "txType": "create",
            "mint": "A",
            "name": "n",
            "image": "i",
            "timestamp": (NOW - 300) * 1000,
        },
        NOW,
    )
    assert mon.sweep(NOW) == []
    assert skips == [("A", "data_unavailable")]
    assert mon.pending == {}


# --- socket event parsing -------------------------------------------------


def test_parse_create_event() -> None:
    token = parse_create_event(
        {
            "txType": "create",
            "mint": "M",
            "name": "Cat",
            "image": "i",
            "vSolInBondingCurve": 8.5,
            "marketCapSol": 100.0,
            "timestamp": (NOW - 300) * 1000,
        },
        NOW,
    )
    assert token is not None
    assert token.mint == "M"
    assert token.created_timestamp == pytest.approx(NOW - 300)
    expected = 8_500_000_000 / CURVE_COMPLETION_LAMPORTS
    assert token.curve_progress == pytest.approx(expected)


def test_parse_create_event_second_timestamps() -> None:
    token = parse_create_event(
        {"txType": "created", "mint": "M", "createdTimestamp": NOW - 300}, NOW
    )
    assert token is not None and token.created_timestamp == pytest.approx(NOW - 300)


def test_parse_create_event_missing_timestamp_uses_now() -> None:
    token = parse_create_event({"txType": "create", "mint": "M"}, NOW)
    assert token is not None and token.created_timestamp == NOW


def test_parse_ignores_trades() -> None:
    assert parse_create_event({"txType": "buy", "mint": "Abc"}, NOW) is None
    assert parse_create_event({"txType": "create"}, NOW) is None


# --- monitor buffer --------------------------------------------------------


def test_new_launch_is_buffered_not_emitted() -> None:
    skips: list = []
    mon = make_monitor(skips)
    assert (
        mon.handle_event({"txType": "create", "mint": "A", "name": "n", "image": "i"}, NOW) is None
    )
    assert "A" in mon.pending


def test_token_emitted_once_evidence_observed() -> None:
    """Maturation path without the deleted trade leg: buyer evidence arrives
    outside the socket (Phase 4 pipeline), the sweep then emits the token."""
    skips: list = []
    mon = make_monitor(skips)
    mon.handle_event(
        {
            "txType": "create",
            "mint": "A",
            "name": "n",
            "image": "i",
            "traderPublicKey": "creator",
            "timestamp": (NOW - 300) * 1000,
        },
        NOW,
    )
    mon.pending["A"].unique_buyers = 3
    ready = mon.sweep(NOW)
    assert [t.mint for t in ready] == ["A"]
    assert "A" not in mon.pending
    assert skips == []


def test_buy_events_do_not_feed_buyer_count() -> None:
    """Socket buys are ignored: the filter must never see phantom evidence."""
    skips: list = []
    mon = make_monitor(skips)
    mon.handle_event(
        {
            "txType": "create",
            "mint": "A",
            "name": "n",
            "image": "i",
            "timestamp": (NOW - 300) * 1000,
        },
        NOW,
    )
    for _ in range(10):
        out = mon.handle_event({"txType": "buy", "mint": "A", "traderPublicKey": "same"}, NOW)
    assert out is None
    assert mon.pending["A"].unique_buyers is None


def test_curve_overflow_skips_permanently() -> None:
    skips: list = []
    mon = make_monitor(skips)
    mon.handle_event(
        {
            "txType": "create",
            "mint": "A",
            "name": "n",
            "image": "i",
            "timestamp": (NOW - 300) * 1000,
            "vSolInBondingCurve": 76.5,
        },
        NOW,
    )
    assert mon.sweep(NOW) == []
    assert "A" not in mon.pending
    assert skips == [("A", "curve_too_full")]


def test_sweep_drops_stale_launches() -> None:
    skips: list = []
    mon = make_monitor(skips)
    mon.handle_event(
        {
            "txType": "create",
            "mint": "A",
            "name": "n",
            "image": "i",
            "timestamp": (NOW - 5000) * 1000,
        },
        NOW,
    )
    mon.pending["A"].unique_buyers = 0  # observed few: buffered, then stale
    ready = mon.sweep(NOW)
    assert ready == []
    assert skips == [("A", "stale_no_traction")]
    assert mon.pending == {}


def test_sweep_emits_nothing_without_evidence() -> None:
    """An old token with no buyer evidence is skipped data_unavailable,
    never emitted and never re-offered."""
    skips: list = []
    mon = make_monitor(skips)
    mon.handle_event(
        {
            "txType": "create",
            "mint": "A",
            "name": "n",
            "image": "i",
            "timestamp": (NOW - 300) * 1000,
        },
        NOW,
    )
    assert mon.sweep(NOW) == []
    assert skips == [("A", "data_unavailable")]


def test_few_buyers_stays_buffered() -> None:
    """An observed low count is temporary: the token waits for the TTL."""
    skips: list = []
    mon = make_monitor(skips)
    mon.handle_event(
        {
            "txType": "create",
            "mint": "A",
            "name": "n",
            "image": "i",
            "timestamp": (NOW - 300) * 1000,
        },
        NOW,
    )
    mon.pending["A"].unique_buyers = 0
    assert mon.sweep(NOW) == []
    assert "A" in mon.pending
    assert skips == []


# --- monitor memory --------------------------------------------------------


def test_seen_set_forgets_oldest() -> None:
    """The process lives for days: the seen-mint list must not grow forever."""
    seen = SeenSet(maxlen=3)
    for mint in ("A", "B", "C", "D"):
        seen.add(mint)
    assert len(seen) == 3
    assert "A" not in seen
    assert "D" in seen


def test_pending_buffer_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(monitor_module, "MAX_PENDING", 3)
    skips: list = []
    mon = make_monitor(skips)
    for index in range(5):
        mon.handle_event(
            {
                "txType": "create",
                "mint": f"M{index}",
                "name": "n",
                "image": "i",
                "timestamp": (NOW - 1000 + index) * 1000,
            },
            NOW,
        )
    assert len(mon.pending) <= 3
    assert skips and skips[0][1] == "buffer_overflow"


# --- socket stream ----------------------------------------------------------


class FakeWebSocket:
    """Socket yielding scripted raw messages, then hanging until cancelled."""

    def __init__(self, script: list[str]) -> None:
        self._script = list(script)
        self.sent: list[dict] = []

    async def __aenter__(self) -> FakeWebSocket:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def send(self, text: str) -> None:
        self.sent.append(json.loads(text))

    async def recv(self) -> str:
        if self._script:
            return self._script.pop(0)
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class FailingWebSocket(FakeWebSocket):
    """First recv raises, proving the reconnect path."""

    async def recv(self) -> str:
        raise ConnectionError("boom")


def patch_connect(
    monkeypatch: pytest.MonkeyPatch, sockets: list, opened: list, kwargs_seen: list
) -> None:
    def fake_connect(url: str, **kwargs: Any) -> FakeWebSocket:
        opened.append(url)
        kwargs_seen.append(kwargs)
        socket = sockets.pop(0)
        if isinstance(socket, Exception):
            raise socket
        return socket

    monkeypatch.setattr(monitor_module, "connect", fake_connect)


def _create_raw(mint: str = "A") -> str:
    return json.dumps(
        {
            "txType": "create",
            "mint": mint,
            "name": "Cat",
            "image": "i",
            "timestamp": (NOW - 300) * 1000,
        }
    )


async def _run_briefly(mon: LaunchMonitor, delay: float = 0.1) -> None:
    async def collect() -> None:
        async for _ in mon.stream():
            pass

    task = asyncio.create_task(collect())
    await asyncio.sleep(delay)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def test_stream_sends_only_subscribe_new_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skips: list = []
    mon = make_monitor(skips, ManualClock(NOW))
    ws = FakeWebSocket([_create_raw()])
    opened: list = []
    kwargs_seen: list = []
    patch_connect(monkeypatch, [ws], opened, kwargs_seen)
    await _run_briefly(mon)

    assert opened == [mon.data.ws_url]
    assert kwargs_seen == [{"proxy": None, "max_queue": mon.data.ws_max_queue}]
    methods = [m["method"] for m in ws.sent]
    assert methods == ["subscribeNewToken"]
    assert "A" in mon.pending  # buffered, never matured over the wire


async def test_stream_reconnects_after_drop(monkeypatch: pytest.MonkeyPatch) -> None:
    skips: list = []
    mon = make_monitor(skips, ManualClock(NOW))
    ws = FakeWebSocket([_create_raw("B")])
    opened: list = []
    kwargs_seen: list = []
    patch_connect(monkeypatch, [FailingWebSocket([]), ws], opened, kwargs_seen)
    await _run_briefly(mon, delay=1.5)

    assert len(opened) == 2  # first connect dropped, second one worked
    assert "B" in mon.pending


async def test_stream_survives_broken_json(monkeypatch: pytest.MonkeyPatch) -> None:
    skips: list = []
    mon = make_monitor(skips, ManualClock(NOW))
    ws = FakeWebSocket(["{broken", _create_raw("C")])
    opened: list = []
    kwargs_seen: list = []
    patch_connect(monkeypatch, [ws], opened, kwargs_seen)
    await _run_briefly(mon)

    assert "C" in mon.pending
