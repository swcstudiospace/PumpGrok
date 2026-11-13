"""An idle event desk makes zero Grok calls (EVT-12).

A full event-mode desk runs 24 virtual hours with no source events. Only the event-mode timers
(risk 5 s, exit 15 s, journal 300 s) wake seats. Grok calls are counted from the real
``GrokGateway``: a class-level spy records every construction and every transport invocation of
the production gateway, so no count is copied from a constant. A positive control admits one
request through the same spy, so a silent counter cannot pass as a zero.

The count is checked after every tick and the run stops at the first observed call.

``PUMPGROK_IDLE_GROK_CANARY=1`` injects one admitted gateway call at the start of the idle window.
The idle gate (``ci/gates/check_idle_grok.py``) runs the file both ways and requires the canary
run to fail with ``IDLE_GROK_CALLS``. The 24-hour test is marked ``slow`` because the replay
ledger scan makes it take minutes; the gate runs it in CI, and ``make test`` excludes it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.config.settings import FilterSettings
from pumpgrok.grok.budget import LayeredBudget
from pumpgrok.grok.cache import ResponseCache
from pumpgrok.grok.gateway import Candidate, GrokGateway, GrokRequest, GrokTransport
from pumpgrok.replay.clock import Clock, FixtureClock
from pumpgrok.supervisor.scheduler import Supervisor
from pumpgrok.supervisor.scheduler.serve import build_serve_replay
from pumpgrok.supervisor.scheduler.wake import EVENT_TIMERS

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "tests" / "fixtures" / "replay" / "smoke"
SEED = 20260101
IDLE_SECONDS = 24 * 3600
#: The shortest event-mode timer period. Ticking on this grid visits every due timer.
STEP_S = int(min(EVENT_TIMERS.values()))
CANARY_ENV = "PUMPGROK_IDLE_GROK_CANARY"
START = 1_800_000_000.0
PROMPT_SHA = "e" * 64


@dataclass
class GrokObservations:
    """What the production gateway reported: constructions, admissions and transport calls."""

    gateways: int = 0
    admissions: list[str] = field(default_factory=list)
    transport_calls: list[str] = field(default_factory=list)


class _ObservedTransport:
    """Wraps the caller's transport so each real invocation is recorded before it runs."""

    def __init__(self, inner: GrokTransport, observations: GrokObservations) -> None:
        self._inner = inner
        self._observations = observations

    async def __call__(self, request: GrokRequest, text: str) -> str:
        self._observations.transport_calls.append(request.event_id)
        return await self._inner(request, text)


@pytest.fixture
def grok(monkeypatch: pytest.MonkeyPatch) -> GrokObservations:
    observations = GrokObservations()
    original_init = GrokGateway.__init__
    original_admit = GrokGateway.admit

    def observed_init(
        self: GrokGateway,
        *,
        clock: Clock,
        transport: GrokTransport,
        cache: ResponseCache,
        budget: LayeredBudget,
    ) -> None:
        observations.gateways += 1
        original_init(
            self,
            clock=clock,
            transport=_ObservedTransport(transport, observations),
            cache=cache,
            budget=budget,
        )

    async def observed_admit(self: GrokGateway, request: GrokRequest) -> Any:
        observations.admissions.append(request.event_id)
        return await original_admit(self, request)

    monkeypatch.setattr(GrokGateway, "__init__", observed_init)
    monkeypatch.setattr(GrokGateway, "admit", observed_admit)
    return observations


def _request(event_id: str, now: float) -> GrokRequest:
    """A request the real prefilter admits at ``now``: old enough, young enough, enough buyers."""
    return GrokRequest(
        event_id=event_id,
        agent="narrative",
        model="grok-test",
        prompt_sha=PROMPT_SHA,
        schema="verdict.v1",
        input={"mint": "MINT1"},
        text="injected",
        candidate=Candidate(
            mint="MINT1",
            created_at=now - 600,
            first_trade_at=now - 300,
            unique_buyers=9,
            prerank=Decimal("0.8"),
            last_decision_at=None,
        ),
    )


class _FakeTransport:
    """Stands in for the x.ai wire. The gateway above it is the production class."""

    async def __call__(self, _request: GrokRequest, _text: str) -> str:
        return '{"verdict":"ok"}'


async def _inject_gateway_call(clock: Clock, tmp_path: Path) -> None:
    """Admit one request through a real gateway on the desk's own clock."""
    gateway = GrokGateway(
        clock=clock,
        transport=_FakeTransport(),
        cache=ResponseCache(tmp_path / "canary-cache.sqlite", clock),
        budget=LayeredBudget(tmp_path / "canary-budget.sqlite", clock),
    )
    outcome = await gateway.admit(_request("canary", clock.now()))
    assert outcome.status == "fresh"


def _calls_seen(grok: GrokObservations) -> int:
    return len(grok.transport_calls) + len(grok.admissions)


async def _run_idle_day(
    supervisor: Supervisor, grok: GrokObservations, tmp_path: Path, *, canary: bool
) -> dict[str, int]:
    """Advance 24 virtual hours in 5 s steps, ticking the desk at each step. No source events.

    The first step optionally injects one admitted call; the run stops at the first call seen.
    """
    clock = supervisor.clock
    origin = clock.now()
    started: dict[str, int] = {}
    crashes: list[tuple[float, str]] = []
    for step in range(1, IDLE_SECONDS // STEP_S + 1):
        clock.advance_to(origin + step * STEP_S)
        if canary and step == 1:
            await _inject_gateway_call(clock, tmp_path)
        if _calls_seen(grok):
            raise AssertionError(
                f"IDLE_GROK_CALLS={len(grok.transport_calls)} "
                f"admissions={len(grok.admissions)} at +{clock.now() - origin:.0f}s"
            )
        outcomes = await supervisor.tick_once()
        for seat, outcome in outcomes.items():
            if outcome == "crash":
                crashes.append((clock.now(), seat))
            started[seat] = started.get(seat, 0) + 1
    assert clock.now() - origin == IDLE_SECONDS
    assert not crashes, crashes[:5]
    return started


async def test_observations_count_an_admitted_gateway_call(
    tmp_path: Path, grok: GrokObservations
) -> None:
    """Positive control: the spy sees the real gateway admit and invoke its transport once."""
    clock = FixtureClock(start=START)
    gateway = GrokGateway(
        clock=clock,
        transport=_FakeTransport(),
        cache=ResponseCache(tmp_path / "cache.sqlite", clock),
        budget=LayeredBudget(tmp_path / "budget.sqlite", clock),
    )
    outcome = await gateway.admit(_request("control", START))
    assert outcome.status == "fresh"
    assert grok.gateways == 1
    assert grok.admissions == ["control"]
    assert grok.transport_calls == ["control"]


@pytest.mark.slow
async def test_idle_event_desk_makes_zero_grok_calls_over_24_virtual_hours(
    tmp_path: Path, grok: GrokObservations
) -> None:
    supervisor, _metrics, store = build_serve_replay(
        SMOKE,
        FilterSettings(),
        seed=SEED,
        ledger_path=tmp_path / "ledger.sqlite",
        wake_mode="event",
    )
    try:
        canary = os.environ.get(CANARY_ENV) == "1"
        started = await _run_idle_day(supervisor, grok, tmp_path, canary=canary)
        # The desk really ran: its three timers fired across the whole day.
        assert started["bot-02-risk"] >= IDLE_SECONDS // 5
        assert started["bot-06-exit"] >= IDLE_SECONDS // 15
        assert started["bot-09-journal"] >= IDLE_SECONDS // 300
        assert _calls_seen(grok) == 0, f"IDLE_GROK_CALLS={len(grok.transport_calls)}"
    finally:
        store.close()
