"""Event review status is independent from decoding and curve review."""

from __future__ import annotations

import base64
import struct

import pytest

from pumpgrok.tools.onchain import curve_layout, pump_events

# CompleteEvent: three public keys and an i64 timestamp, with its Anchor discriminator.
_COMPLETE_EVENT = bytes.fromhex("5f72619cd42e9808") + bytes(96) + struct.pack("<q", 123)


def test_successful_decode_does_not_promote_assumed_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "VERIFIED")
    assert pump_events.EVENT_DECODE_STATUS == "ASSUMED"

    event = pump_events.decode_event(_COMPLETE_EVENT)
    program_event = pump_events.decode_program_data(base64.b64encode(_COMPLETE_EVENT).decode())

    assert event.timestamp == 123
    assert program_event == event
    assert pump_events.EVENT_DECODE_STATUS == "ASSUMED"
    assert curve_layout.LAYOUT_STATUS == "VERIFIED"


def test_simulated_reviewed_status_remains_independent_of_layout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "ASSUMED")
    event = pump_events.decode_event(_COMPLETE_EVENT)
    assert event.timestamp == 123
    assert pump_events.EVENT_DECODE_STATUS == "ASSUMED"

    # Simulate an independently approved status; this is not a human approval.
    monkeypatch.setattr(pump_events, "EVENT_DECODE_STATUS", "VERIFIED")
    assert pump_events.decode_event(_COMPLETE_EVENT) == event
    assert pump_events.EVENT_DECODE_STATUS == "VERIFIED"
    assert curve_layout.LAYOUT_STATUS == "ASSUMED"
