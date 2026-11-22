"""Manifest carries filenames and counts only; key set pinned (T-13-01c)."""

from __future__ import annotations

import json
from pathlib import Path

from pumpgrok.datafeed.events import CurveTick
from pumpgrok.replay.clock import format_ts_utc
from pumpgrok.replay.live_recorder import LiveRecorder

EXPECTED_KEYS = {
    "dataset",
    "recorded_from_utc",
    "recorded_to_utc",
    "seed_hint",
    "sources",
    "sha256",
    "notes",
}


def test_manifest_key_set_and_no_secrets(tmp_path: Path) -> None:
    directory = tmp_path / "ds"
    recorder = LiveRecorder(directory)
    recorder.record_tick(
        CurveTick.model_validate(
            {
                "mint": "m1",
                "ts_utc": format_ts_utc(1_000.0),
                "virtual_sol_reserves_lamports": 42_000_000_000,
                "virtual_token_reserves_units": 766_428_571,  # pragma: allowlist secret
                "real_sol_reserves_lamports": 12_000_000_000,
                "real_token_reserves_units": 500_000_000_000,
                "total_supply_units": 1_000_000_000_000,
                "complete": False,
            }
        )
    )
    recorder.seal("ds")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest) == EXPECTED_KEYS
    text = json.dumps(manifest)
    assert "private" not in text
    assert "key" not in text.lower().replace("key_set", "")
