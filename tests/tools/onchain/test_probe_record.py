"""Probe record never self-verifies (MKT-03/MKT-10)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

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


def test_record_doc_never_writes_verified(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "probe", Path(__file__).resolve().parents[3] / "scripts" / "probe_pump_accounts.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out = tmp_path / "probe-record.md"
    module.write_record_doc({"status": "decoded_pending_review"}, out)
    text = out.read_text(encoding="utf-8")
    assert "decoded_pending_review" in text
    assert "Status: VERIFIED" not in text
    module.write_record_doc(
        {"status": "ASSUMED", "error": "no bonding-curve account configured"}, out
    )
    text = out.read_text(encoding="utf-8")
    assert "Status: ASSUMED" in text
    assert "no bonding-curve account configured" in text
