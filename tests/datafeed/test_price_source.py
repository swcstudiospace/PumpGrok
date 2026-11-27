"""LivePriceSource fail-closed matrix (MKT-07)."""

from __future__ import annotations

import random
from pathlib import Path

from pumpgrok.datafeed.events import CurveObservation, CurveTick, GapEvent
from pumpgrok.datafeed.price import LivePriceSource
from pumpgrok.events.sources import SourceSupervisor
from pumpgrok.replay.clock import FixtureClock

TS = "2026-11-21T00:00:00.000000Z"
TS30 = "2026-11-21T00:00:30.000000Z"
T0 = 1_795_219_200.0  # epoch of TS


def _tick(mint: str = "m1", *, complete: bool = False, source: str = "replay") -> CurveTick:
    return CurveTick.model_validate(
        {
            "mint": mint,
            "ts_utc": TS,
            "virtual_sol_reserves_lamports": 42_000_000_000,
            "virtual_token_reserves_units": 766_428_571,  # pragma: allowlist secret
            "real_sol_reserves_lamports": 12_000_000_000,
            "real_token_reserves_units": 500_000_000_000,
            "total_supply_units": 1_000_000_000_000,
            "complete": complete,
            "curve_source": source,
        }
    )


def _observation(mint: str = "m1", *, complete: bool = False) -> CurveObservation:
    return CurveObservation(
        mint=mint,
        ts_utc=TS,
        s_lamports=42_000_000_000,
        t_units=766_428_571,
        complete=complete,
        source="rpc",
    )


def _source(
    tmp_path: Path, *, max_age_s: float = 10.0
) -> tuple[FixtureClock, SourceSupervisor, LivePriceSource]:
    clock = FixtureClock(T0)
    health = SourceSupervisor(clock, random.Random(0), path=tmp_path / "cursor.db")
    health.note_frame()
    src = LivePriceSource(clock=clock, health=health, max_age_s=max_age_s, max_observations=4)
    return clock, health, src


async def test_disconnected_yields_none(tmp_path: Path) -> None:
    _, health, src = _source(tmp_path)
    health.note_failure()
    assert await src.curve("m1") is None
    src.on_tick(_tick())
    assert src.entry_allowed("m1") is False
    health.close()


async def test_connected_observation_prices(tmp_path: Path) -> None:
    _, health, src = _source(tmp_path)
    src.on_tick(_tick())
    src.observe(_observation())
    snapshot = await src.curve("m1")
    assert snapshot is not None
    assert snapshot.s_lamports == 42_000_000_000
    assert snapshot.source == "rpc"
    # Entry stays fail-closed: no replay provenance is admitted yet.
    assert src.entry_allowed("m1") is False
    health.close()


async def test_rpc_never_prices_while_not_live(tmp_path: Path) -> None:
    _, health, src = _source(tmp_path)
    health.note_failure()
    src.observe(_observation())
    assert await src.curve("m1") is None
    src.on_tick(_tick(source="rpc"))
    assert src.entry_allowed("m1") is False
    health.close()


async def test_completed_curve_refuses_entry(tmp_path: Path) -> None:
    _, health, src = _source(tmp_path)
    src.on_tick(_tick(complete=True))
    src.observe(_observation(complete=True))
    assert src.entry_allowed("m1") is False
    # Price still readable for exit marks; the refusal is entry-only.
    snapshot = await src.curve("m1")
    assert snapshot is not None
    assert snapshot.s_lamports == 42_000_000_000
    assert snapshot.complete is True
    health.close()


async def test_gap_holds_position(tmp_path: Path) -> None:
    clock, health, src = _source(tmp_path, max_age_s=120.0)
    src.observe(_observation())
    src.on_tick(_tick())
    assert src.is_stale("m1") is False
    src.on_gap(
        GapEvent.model_validate(
            {
                "mint": "m1",
                "ts_utc": TS30,
                "reason": "timeout",
                "from_ts_utc": TS,
                "to_ts_utc": TS30,
            }
        )
    )
    assert src.is_stale("m1") is True
    clock.advance_to(T0 + 30.0)
    snapshot = await src.curve("m1")
    assert snapshot is not None
    assert snapshot.s_lamports == 42_000_000_000  # held, not new
    health.close()


async def test_timeout_yields_none(tmp_path: Path) -> None:
    clock, health, src = _source(tmp_path, max_age_s=120.0)
    src.observe(_observation())
    snapshot = await src.curve("m1")
    assert snapshot is not None
    assert snapshot.s_lamports == 42_000_000_000
    clock.advance_to(T0 + 200.0)
    assert await src.curve("m1") is None
    health.close()
