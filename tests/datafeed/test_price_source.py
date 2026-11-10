"""Paper prices require fresh, independently admitted live observations."""

import random
from dataclasses import replace
from pathlib import Path

import pytest

from pumpgrok.datafeed.events import CurveObservation
from pumpgrok.datafeed.price import LivePriceSource
from pumpgrok.events.sources import STALE_AFTER_S, SourceSupervisor
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools.onchain import curve_layout

MINT = "mint-1"
START = 1_767_225_600.0


@pytest.fixture
def source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    clock = FixtureClock(START)
    health = SourceSupervisor(clock, random.Random(0), path=tmp_path / "cursor.db")
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "VERIFIED")
    prices = LivePriceSource(clock=clock, health=health, max_age_s=10.0)
    yield prices, health, clock
    health.close()


def observation(clock: FixtureClock, *, source: str = "rpc", complete: bool = False):
    return CurveObservation(
        mint=MINT,
        ts_utc=clock.utc_iso(),
        s_lamports=42_000_000_000,
        t_units=766_428_571_428_571,
        complete=complete,
        source=source,
    )


async def test_verified_fresh_live_observation_prices_with_non_fixture_provenance(source):
    prices, health, clock = source
    health.note_frame()
    prices.observe(observation(clock))
    snapshot = await prices.curve(MINT)
    assert snapshot is not None
    assert (snapshot.s_lamports, snapshot.t_units) == (42_000_000_000, 766_428_571_428_571)
    assert snapshot.mint == MINT
    assert snapshot.source == "rpc"
    assert snapshot.source != "fixture"
    assert snapshot.ts == clock.now()


async def test_never_framed_and_disconnected_fail_closed(source):
    prices, health, clock = source
    prices.observe(observation(clock))
    # SourceSupervisor alone reports a never-framed source as live.
    assert await prices.curve(MINT) is None
    health.note_frame()
    assert await prices.curve(MINT) is not None
    health.note_failure()
    assert await prices.curve(MINT) is None
    health.note_frame()
    assert await prices.curve(MINT) is not None


async def test_stale_observation_and_stale_connection_independently_fail_closed(source):
    prices, health, clock = source
    health.note_frame()
    prices.observe(observation(clock))
    assert await prices.curve(MINT) is not None
    clock.advance_to(START + 11)
    health.note_frame()
    assert await prices.curve(MINT) is None
    prices.observe(observation(clock))
    assert await prices.curve(MINT) is not None
    clock.advance_to(clock.now() + STALE_AFTER_S + 1)
    prices.observe(observation(clock))
    assert await prices.curve(MINT) is None


async def test_assumed_status_revokes_existing_live_observation_dynamically(source, monkeypatch):
    prices, health, clock = source
    health.note_frame()
    prices.observe(observation(clock))
    assert await prices.curve(MINT) is not None
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "ASSUMED")
    assert await prices.curve(MINT) is None
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "VERIFIED")
    assert await prices.curve(MINT) is not None


@pytest.mark.parametrize("label", ["fixture", "unknown", "unverified"])
async def test_live_ingestion_cannot_forge_replay_or_admit_unknown_sources(source, label):
    prices, health, clock = source
    health.note_frame()
    prices.observe(observation(clock, source=label))
    assert await prices.curve(MINT) is None

async def test_unknown_mint_and_future_observation_are_unavailable(source):
    prices, health, clock = source
    health.note_frame()
    prices.observe(replace(observation(clock), ts_utc="2099-01-01T00:00:00Z"))
    assert await prices.curve(MINT) is None
    assert await prices.curve("unknown") is None


@pytest.mark.parametrize("max_age_s", [0, -1, float("inf"), float("nan")])
def test_freshness_budget_must_be_explicit_and_valid(source, max_age_s):
    _, health, clock = source
    with pytest.raises(ValueError):
        LivePriceSource(clock=clock, health=health, max_age_s=max_age_s)
