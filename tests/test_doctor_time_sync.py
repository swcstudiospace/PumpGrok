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
