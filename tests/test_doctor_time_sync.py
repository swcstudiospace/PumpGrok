"""Doctor reports host clock synchronization (report only, never fatal).

The probe is `timedatectl show --property=NTPSynchronized --value`. `yes` is ok; `no` or an
unknown reading is info, because the doctor's warn shape is fixed by the existing report tests.
"""

from __future__ import annotations

import subprocess

import pytest

from pumpgrok import doctor
from pumpgrok.config.settings import Settings


def test_synchronized_clock_is_ok() -> None:
    assert doctor.clock_sync_line(probe=lambda: True) == "ok    clock-sync (NTP synchronized)"


def test_unsynchronized_clock_is_info() -> None:
    line = doctor.clock_sync_line(probe=lambda: False)
    assert line == "info  clock-sync (not NTP-synchronized; wall clock may drift)"


def test_unknown_clock_state_is_info() -> None:
    line = doctor.clock_sync_line(probe=lambda: None)
    assert line == "info  clock-sync (unknown: timedatectl unavailable)"


class _Completed:
    def __init__(self, returncode: int, stdout: str) -> None:
        self.returncode = returncode
        self.stdout = stdout


def test_timedatectl_yes_reads_synchronized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/timedatectl")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Completed(0, "yes\n"))
    assert doctor.timedatectl_synchronized() is True


def test_timedatectl_no_reads_unsynchronized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/timedatectl")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Completed(0, "no\n"))
    assert doctor.timedatectl_synchronized() is False


def test_missing_timedatectl_reads_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    assert doctor.timedatectl_synchronized() is None


def test_timedatectl_failure_reads_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/timedatectl")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Completed(1, ""))
    assert doctor.timedatectl_synchronized() is None


def test_timedatectl_timeout_reads_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    def timed_out(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="timedatectl", timeout=2.0)

    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/timedatectl")
    monkeypatch.setattr(subprocess, "run", timed_out)
    assert doctor.timedatectl_synchronized() is None


def test_clock_line_sits_before_summary_and_is_never_warn(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(doctor, "timedatectl_synchronized", lambda: True)
    lines = doctor.doctor_report(Settings(mode="paper"))
    clock = [line for line in lines if "clock-sync" in line]
    assert clock == ["ok    clock-sync (NTP synchronized)"]
    assert lines.index(clock[0]) < len(lines) - 1
    assert lines[-1].startswith("doctor:")
