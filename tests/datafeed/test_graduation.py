"""Graduation and data gaps must not manufacture a paper sale."""

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from pumpgrok.datafeed.graduation import GapSettings, PositionAction, entry_allowed, position_action
from pumpgrok.execution import verify_replay
from pumpgrok.execution.paper_adapter.models import CurveSnapshot
from pumpgrok.execution.paper_factory import VerifiedReplay
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.tools.onchain import curve_layout

MINT = "mint-1"
S0 = 42_000_000_000
T0 = 766_428_571_428_571


def snapshot(*, complete: bool = False, source: str = "rpc") -> CurveSnapshot:
    return CurveSnapshot(
        mint=MINT,
        s_lamports=S0,
        t_units=T0,
        complete=complete,
        source=source,
        ts=100.0,
    )


def _verified(
    root: Path, *, ts: float, complete: bool = False
) -> tuple[CurveSnapshot, VerifiedReplay]:
    """Read one tick at ``ts`` through a verify_replay binding over its own dataset."""
    dataset = root / f"replay-{ts:g}-{'complete' if complete else 'open'}"
    dataset.mkdir(parents=True)
    tick = {
        "ts_utc": format_ts_utc(ts),
        "kind": "tick",
        "mint": MINT,
        "S": S0,
        "T": T0,
        "complete": complete,
        "source": "rest",
    }
    data = (json.dumps(tick, separators=(",", ":")) + "\n").encode()
    (dataset / "events.jsonl").write_bytes(data)
    manifest = {
        "dataset": dataset.name,
        "recorded_from_utc": format_ts_utc(ts),
        "recorded_to_utc": format_ts_utc(ts),
        "seed_hint": 7,
        "sha256": {"events.jsonl": hashlib.sha256(data).hexdigest()},
    }
    (dataset / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    replay = verify_replay(dataset, FixtureClock(start=ts))
    read = asyncio.run(replay.curves.curve(MINT))
    assert read is not None and read.source == "fixture" and read.ts == ts
    return read, replay


def test_open_verified_curve_allows_entry_but_completed_curve_denies_it(monkeypatch, tmp_path):
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "VERIFIED")
    open_snap, open_replay = _verified(tmp_path, ts=100.0)
    done_snap, done_replay = _verified(tmp_path, ts=100.0, complete=True)
    assert entry_allowed(open_snap, now=100.0, max_age_s=10.0, replay=open_replay) is True
    assert entry_allowed(done_snap, now=100.0, max_age_s=10.0, replay=done_replay) is False
    assert entry_allowed(None, now=100.0, max_age_s=10.0) is False


def test_assumed_or_unknown_live_curve_never_authorizes_entry(monkeypatch):
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "ASSUMED")
    assert entry_allowed(snapshot(), now=100.0, max_age_s=10.0) is False
    assert entry_allowed(snapshot(source="unknown"), now=100.0, max_age_s=10.0) is False
    # A bare fixture label has no verified replay binding behind it: refused.
    assert entry_allowed(snapshot(source="fixture"), now=100.0, max_age_s=10.0) is False


def test_gap_holds_then_timeout_marks_zero_without_a_sale(monkeypatch, tmp_path):
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "VERIFIED")
    settings = GapSettings(gap_after_s=10.0, timeout_after_s=30.0)
    open_snap, replay = _verified(tmp_path, ts=100.0)
    assert (
        position_action(
            open_snap, last_trusted_at=100.0, now=100.0, settings=settings, replay=replay
        )
        == PositionAction.MARK
    )
    assert (
        position_action(None, last_trusted_at=100.0, now=110.0, settings=settings)
        == PositionAction.HOLD
    )
    assert (
        position_action(None, last_trusted_at=100.0, now=129.999, settings=settings)
        == PositionAction.HOLD
    )
    assert (
        position_action(None, last_trusted_at=100.0, now=130.0, settings=settings)
        == PositionAction.ZERO_MARK
    )


def test_completed_curve_is_distinct_from_gap_and_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "VERIFIED")
    settings = GapSettings(gap_after_s=10.0, timeout_after_s=30.0)
    done_snap, replay = _verified(tmp_path, ts=100.0, complete=True)
    assert (
        position_action(
            done_snap, last_trusted_at=100.0, now=101.0, settings=settings, replay=replay
        )
        == PositionAction.GRADUATED
    )


def test_unverified_or_stale_snapshot_cannot_supply_a_mark(monkeypatch):
    settings = GapSettings(gap_after_s=10.0, timeout_after_s=30.0)
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "ASSUMED")
    assert (
        position_action(snapshot(), last_trusted_at=100.0, now=105.0, settings=settings)
        == PositionAction.HOLD
    )
    assert (
        position_action(
            snapshot(complete=True), last_trusted_at=100.0, now=130.0, settings=settings
        )
        == PositionAction.ZERO_MARK
    )
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "VERIFIED")
    assert (
        position_action(snapshot(), last_trusted_at=100.0, now=111.0, settings=settings)
        == PositionAction.HOLD
    )
    assert (
        position_action(
            snapshot(source="unknown"), last_trusted_at=100.0, now=105.0, settings=settings
        )
        == PositionAction.HOLD
    )


@pytest.mark.parametrize(
    ("gap", "timeout"),
    [(0, 30), (-1, 30), (10, 0), (10, 9), (float("nan"), 30), (10, float("inf"))],
)
def test_gap_and_timeout_settings_are_validated(gap, timeout):
    with pytest.raises(ValueError):
        GapSettings(gap_after_s=gap, timeout_after_s=timeout)


def test_entry_checks_snapshot_freshness_against_explicit_clock_and_budget(monkeypatch, tmp_path):
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "VERIFIED")
    current, replay = _verified(tmp_path, ts=100.0)
    assert entry_allowed(current, now=105.0, max_age_s=10.0, replay=replay) is True
    assert entry_allowed(current, now=111.0, max_age_s=10.0, replay=replay) is False
    assert entry_allowed(current, now=99.0, max_age_s=10.0, replay=replay) is False
    assert (
        entry_allowed(
            current.model_copy(update={"ts": None}), now=105.0, max_age_s=10.0, replay=replay
        )
        is False
    )


def test_future_last_trusted_time_fails_closed_instead_of_suppressing_timeout():
    settings = GapSettings(gap_after_s=10.0, timeout_after_s=30.0)
    with pytest.raises(ValueError):
        position_action(None, last_trusted_at=200.0, now=150.0, settings=settings)


def test_latest_trusted_observation_prevents_premature_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "VERIFIED")
    settings = GapSettings(gap_after_s=10.0, timeout_after_s=30.0)
    recent, replay = _verified(tmp_path, ts=120.0)
    assert (
        position_action(
            recent, last_trusted_at=100.0, now=120.0, settings=settings, replay=replay
        )
        == PositionAction.MARK
    )
    assert (
        position_action(
            recent, last_trusted_at=120.0, now=131.0, settings=settings, replay=replay
        )
        == PositionAction.HOLD
    )
    assert (
        position_action(
            recent, last_trusted_at=120.0, now=150.0, settings=settings, replay=replay
        )
        == PositionAction.ZERO_MARK
    )


def test_unverified_observation_does_not_refresh_timeout(monkeypatch):
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "ASSUMED")
    settings = GapSettings(gap_after_s=10.0, timeout_after_s=30.0)
    recent = snapshot().model_copy(update={"ts": 129.0})
    assert (
        position_action(recent, last_trusted_at=100.0, now=130.0, settings=settings)
        == PositionAction.ZERO_MARK
    )


def test_repeated_stale_snapshots_never_postpone_timeout(monkeypatch):
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "VERIFIED")
    settings = GapSettings(gap_after_s=10.0, timeout_after_s=30.0)
    for stamp in (115.0, 130.0, 145.0):
        stale = snapshot().model_copy(update={"ts": stamp})
        expected = PositionAction.HOLD if stamp + 11.0 < 135.0 else PositionAction.ZERO_MARK
        assert (
            position_action(stale, last_trusted_at=105.0, now=stamp + 11.0, settings=settings)
            == expected
        )
