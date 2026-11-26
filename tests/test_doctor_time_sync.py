<<<<<<< HEAD
"""Time-sync probe runs read-only and carries no host details."""

from pumpgrok.doctor import time_sync_probe


def test_probe_line_is_read_only() -> None:
    line = time_sync_probe()
    assert "time-sync:" in line
    assert "read-only" in line
    assert "not adjusted" in line


def test_probe_carries_no_host_details() -> None:
    line = time_sync_probe()
    assert "http" not in line
    assert "127.0.0.1" not in line
=======
"""Doctor reports host clock synchronization (report only, never fatal).

The probe reads the kernel NTP state (adjtimex STA_UNSYNC, the source timedatectl uses) and
spawns no process. `yes` is ok; `no` or an unknown reading is info, because the doctor's warn
shape is fixed by the existing report tests.
"""

from __future__ import annotations

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


def test_ntp_synchronized_reads_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "_kernel_ntp_state", lambda: (0, 0))
    assert doctor.timedatectl_synchronized() is True


def test_ntp_unsynchronized_reads_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "_kernel_ntp_state", lambda: (0, doctor._STA_UNSYNC))
    assert doctor.timedatectl_synchronized() is False


def test_missing_clock_interface_reads_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable() -> tuple[int, int]:
        raise AttributeError("adjtimex")

    monkeypatch.setattr(doctor, "_kernel_ntp_state", unavailable)
    assert doctor.timedatectl_synchronized() is None


def test_adjtimex_failure_reads_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "_kernel_ntp_state", lambda: (-1, 0))
    assert doctor.timedatectl_synchronized() is None


def test_read_error_reads_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    def read_error() -> tuple[int, int]:
        raise OSError("libc unavailable")

    monkeypatch.setattr(doctor, "_kernel_ntp_state", read_error)
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
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
