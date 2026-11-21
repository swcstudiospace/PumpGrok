"""Probe record never self-verifies (MKT-03/MKT-10)."""

from __future__ import annotations

from pumpgrok.tools.onchain.pump_events import EVENT_DECODE_STATUS, decode_status


def probe_record_status(error: str | None) -> str:
    """What the probe may write: decoded_pending_review or ASSUMED+error."""
    if error:
        return f"ASSUMED error={error}"
    return "decoded_pending_review"


def test_error_records_assumed_with_error() -> None:
    assert probe_record_status("no bonding-curve account configured") == (
        "ASSUMED error=no bonding-curve account configured"
    )


def test_success_is_pending_review_not_verified() -> None:
    assert probe_record_status(None) == "decoded_pending_review"
    assert "VERIFIED" not in probe_record_status(None)
    assert EVENT_DECODE_STATUS == "ASSUMED"
    assert decode_status(reviewed_by=None) == "ASSUMED"
