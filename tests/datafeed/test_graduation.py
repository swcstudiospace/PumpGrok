"""Graduation refusal (MKT-07)."""

from __future__ import annotations

from pumpgrok.datafeed.graduation import entry_refused, graduation_refusal_reason


def test_completed_refuses() -> None:
    assert entry_refused(complete=True) is True
    assert graduation_refusal_reason(complete=True) == "graduated: curve is complete"


def test_incomplete_allowed() -> None:
    assert entry_refused(complete=False) is False
    assert graduation_refusal_reason(complete=False) is None
