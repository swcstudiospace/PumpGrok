"""Seat access grants exist only as operator-choice ledger rows."""

from pathlib import Path

from pumpgrok.onboarding.access import has_access, record_access


def test_no_grant_by_default(tmp_path: Path) -> None:
    assert not has_access(tmp_path / "access.jsonl", "bot-01-scout")


def test_grant_is_recorded(tmp_path: Path) -> None:
    path = tmp_path / "access.jsonl"
    record_access(path, "bot-01-scout")
    assert has_access(path, "bot-01-scout")
    assert not has_access(path, "bot-02-risk")
