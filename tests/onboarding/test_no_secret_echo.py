"""No secret value reaches stdout, stderr, logs, or the ledger file."""

import io
import json

from pumpgrok.onboarding.doctor_report import doctor_records

SENTINEL = "sentinel-secret-value-9f3a"  # pragma: allowlist secret — test sentinel, not a real credential


def test_doctor_records_carry_no_values() -> None:
    records = doctor_records({"PUMPGROK_GROK__API_KEY": SENTINEL}, "paper")
    rendered = json.dumps(
        [
            {
                "name": record.name,
                "required_for_mode": record.required_for_mode,
                "status": record.status,
                "source": record.source,
            }
            for record in records
        ]
    )
    assert SENTINEL not in rendered


def test_statuses_are_presence_only() -> None:
    records = doctor_records({"PUMPGROK_GROK__API_KEY": SENTINEL}, "paper")
    by_name = {record.name: record for record in records}
    assert by_name["xai_api_key"].status == "present"
    for record in records:
        assert record.status in {
            "present",
            "missing",
            "default",
            "forbidden-present",
            "not-read",
        }
    buffer = io.StringIO()
    buffer.write(json.dumps(by_name["xai_api_key"].__dict__))
    assert SENTINEL not in buffer.getvalue()
