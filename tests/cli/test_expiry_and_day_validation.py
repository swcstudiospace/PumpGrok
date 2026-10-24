"""CLI-02 / CLI-03: live confirm expiry is a real UTC instant; report days are real dates.

``live confirm`` refuses a naive or past ``--expires`` and records an offset expiry as the
UTC instant it denotes. ``report`` refuses a ``--day`` or ``--week`` that is not a real
calendar date, with the usage error and exit 1, instead of a traceback or an empty report.
Offline; the working directory is a tmp_path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pumpgrok.cli import EXIT_CONFIG, EXIT_OK, main

_BY = "human:operator"
_CAP = "0.5"
_FAR_FUTURE_PLUS_05 = "2099-01-01T05:00:00+05:00"
_FAR_FUTURE_UTC = "2099-01-01T00:00:00Z"


@pytest.fixture
def confirm_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PUMPGROK_CONFIRMATION_KEY", "test-confirmation-key")
    return tmp_path


def _confirm(expires: str) -> int:
    return main(["live", "confirm", "--by", _BY, "--notional-cap", _CAP, "--expires", expires])


def test_offset_expiry_is_recorded_as_the_utc_instant(
    confirm_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _confirm(_FAR_FUTURE_PLUS_05) == EXIT_OK
    record = json.loads((confirm_env / "var" / "live_confirmation.json").read_text("utf-8"))
    assert record["expires_at"] == _FAR_FUTURE_UTC


def test_zulu_expiry_is_recorded_unchanged(
    confirm_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _confirm("2099-01-01T00:00:00Z") == EXIT_OK
    record = json.loads((confirm_env / "var" / "live_confirmation.json").read_text("utf-8"))
    assert record["expires_at"] == _FAR_FUTURE_UTC


def test_naive_expiry_is_refused(confirm_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _confirm("2099-01-01T00:00:00") == EXIT_CONFIG
    assert "usage error" in capsys.readouterr().err
    assert not (confirm_env / "var" / "live_confirmation.json").exists()


def test_past_expiry_is_refused(confirm_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _confirm("2000-01-01T00:00:00Z") == EXIT_CONFIG
    err = capsys.readouterr().err
    assert "usage error" in err
    assert "past" in err
    assert not (confirm_env / "var" / "live_confirmation.json").exists()


@pytest.mark.parametrize("day", ["garbage", "2026-02-30", "2026-13-01", ""])
def test_daily_report_refuses_a_non_date_day(
    day: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["report", "--daily", "--day", day]) == EXIT_CONFIG
    captured = capsys.readouterr()
    assert "usage error" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


@pytest.mark.parametrize("week", ["garbage", "2026-02-30"])
def test_weekly_report_refuses_a_non_date_week(
    week: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["report", "--weekly", "--week", week]) == EXIT_CONFIG
    captured = capsys.readouterr()
    assert "usage error" in captured.err
    assert captured.out == ""
