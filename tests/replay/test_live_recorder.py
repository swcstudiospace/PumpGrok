"""Sealed dataset passes load_dataset; gaps and torn lines recorded (REC-01/02)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pumpgrok.datafeed.events import CurveTick, GapEvent
from pumpgrok.replay.clock import format_ts_utc
from pumpgrok.replay.fixtures import load_dataset
from pumpgrok.replay.live_recorder import LiveRecorder


def _tick(mint: str, epoch: float) -> CurveTick:
    return CurveTick.model_validate(
        {
            "mint": mint,
            "ts_utc": format_ts_utc(epoch),
            "virtual_sol_reserves_lamports": 42_000_000_000,
            "virtual_token_reserves_units": 766_428_571,
            "real_sol_reserves_lamports": 12_000_000_000,
            "real_token_reserves_units": 500_000_000_000,
            "total_supply_units": 1_000_000_000_000,
            "complete": False,
        }
    )


def test_sealed_dataset_passes_load_dataset(tmp_path: Path) -> None:
    directory = tmp_path / "ds"
    recorder = LiveRecorder(directory)
    recorder.record_tick(_tick("m1", 1_000.0))
    recorder.record_tick(_tick("m1", 2_000.0))
    recorder.seal("ds")
    dataset = load_dataset(directory)
    assert len(dataset.events) == 2
    assert dataset.manifest.dataset == "ds"
    assert str(dataset.events[0]["ts_utc"]) == format_ts_utc(1_000.0)


def test_decreasing_tick_raises(tmp_path: Path) -> None:
    recorder = LiveRecorder(tmp_path / "ds")
    recorder.record_tick(_tick("m1", 2_000.0))
    with pytest.raises(ValueError):
        recorder.record_tick(_tick("m1", 1_000.0))


def test_gap_written_and_sealed(tmp_path: Path) -> None:
    directory = tmp_path / "ds"
    recorder = LiveRecorder(directory)
    recorder.record_tick(_tick("m1", 1_000.0))
    recorder.record_gap(
        GapEvent.model_validate(
            {
                "mint": "m1",
                "ts_utc": format_ts_utc(1_030.0),
                "reason": "timeout",
                "from_ts_utc": format_ts_utc(1_000.0),
                "to_ts_utc": format_ts_utc(1_030.0),
            }
        )
    )
    recorder.seal("ds")
    gaps = (directory / "gaps.jsonl").read_text(encoding="utf-8")
    assert "timeout" in gaps
    dataset = load_dataset(directory)
    assert "gaps.jsonl" in dataset.manifest.sha256


def test_torn_last_line_recovered_on_startup(tmp_path: Path) -> None:
    directory = tmp_path / "ds"
    recorder = LiveRecorder(directory)
    recorder.record_tick(_tick("m1", 1_000.0))
    recorder.seal("ds")
    # Simulate a torn write: append a partial line without newline.
    ticks = directory / "events.jsonl"
    ticks.write_bytes(ticks.read_bytes() + b'{"mint": "m1", "ts_utc": "2026')
    # New recorder recovers, then re-seals cleanly.
    recovered = LiveRecorder(directory)
    assert any("recovered" in note for note in recovered.notes)
    recovered.record_tick(_tick("m1", 2_000.0))
    recovered.seal("ds")
    dataset = load_dataset(directory)
    assert len(dataset.events) == 2
