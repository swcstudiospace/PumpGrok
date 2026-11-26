"""evidence-50 fixture: >= 50 admitted candidates and loads via load_dataset."""

import subprocess
from pathlib import Path

from pumpgrok.replay.clock import parse_ts_utc
from pumpgrok.replay.fixtures import load_dataset


def test_manifest_and_timestamps() -> None:
    dataset = load_dataset(Path("tests/fixtures/replay/evidence-50"))
    assert len(dataset.events) >= 50
    stamps = [parse_ts_utc(str(event["ts_utc"])) for event in dataset.events]
    assert stamps == sorted(stamps)
    assert all(isinstance(event["mint"], str) for event in dataset.events)


def test_admitted_candidates_at_least_50() -> None:
    dataset = load_dataset(Path("tests/fixtures/replay/evidence-50"))
    admitted = {
        event["mint"] for event in dataset.events if (int(event["S"]) // 1_000_000) % 100 >= 50
    }
    assert len(admitted) >= 50


def test_negative_control_budget_too_small() -> None:

    proc = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "scripts/measure_grok_calls.py",
            "--dataset",
            "tests/fixtures/replay/evidence-50",
            "--budget",
            "5",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 2
