"""Manifest carries filenames and counts only; key set pinned (T-13-01c)."""

from __future__ import annotations

import json
from pathlib import Path

from pumpgrok.datafeed.events import CurveObservation
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.live_recorder import LiveRecorder

EXPECTED_KEYS = {
    "dataset",
    "notes",
    "provenance",
    "recorded_from_utc",
    "recorded_to_utc",
    "seed_hint",
    "sha256",
    "sources",
}


def test_manifest_key_set_and_no_secrets(tmp_path: Path) -> None:
    directory = tmp_path / "ds"
    recorder = LiveRecorder(directory, clock=FixtureClock(1_000.0))
    recorder.record(
        CurveObservation(
            mint="m1",
            ts_utc=format_ts_utc(1_000.0),
            s_lamports=42_000_000_000,
            t_units=766_428_571,  # pragma: allowlist secret
            complete=False,
            source="fixture-rpc",
        )
    )
    recorder.seal()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest) == EXPECTED_KEYS
    text = json.dumps(manifest)
    assert "private" not in text
    assert "key" not in text.lower().replace("key_set", "")
