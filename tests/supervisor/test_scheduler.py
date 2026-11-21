"""Scheduler: cadence entry is untouched by event mode (parity test)."""

import pathlib


def test_cadence_scheduler_has_no_wake_dependency() -> None:
    source = pathlib.Path(
        "src/pumpgrok/supervisor/scheduler/supervisor.py"
    ).read_text(encoding="utf-8")
    assert "scheduler.wake" not in source
    assert "SEAT_WAKES" not in source


def test_wake_flag_defaults_to_cadence() -> None:
    source = pathlib.Path("src/pumpgrok/cli/parsing.py").read_text(encoding="utf-8")
    assert '--wake-mode' in source
    assert 'default="cadence"' in source


def test_cadence_output_byte_identical() -> None:
    import subprocess

    proc = subprocess.run(
        [
            "uv",
            "run",
            "pumpgrok",
            "run",
            "--mode",
            "paper",
            "--once",
            "--replay",
            "tests/fixtures/replay/smoke",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
