"""Doctor --json prints one record per input and exits non-zero on failure."""

import json
import subprocess


def test_doctor_json_records_per_input() -> None:
    proc = subprocess.run(
        ["uv", "run", "pumpgrok", "doctor", "--json", "--mode", "paper"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        # Clean-env refusal is also acceptable: missing required inputs.
        assert proc.returncode == 1
    records = json.loads(proc.stdout)
    names = {record["name"] for record in records}
    assert "xai_api_key" in names
    assert "hmac_confirmation_key" in names
    for record in records:
        assert set(record) >= {"name", "required_for_mode", "status", "source"}


def test_doctor_records_module() -> None:
    from pumpgrok.onboarding.doctor_report import doctor_records

    records = doctor_records({}, "paper")
    assert len(records) == 5
    assert {record.name for record in records}.issuperset(
        {"xai_api_key", "wallet_public_address"}
    )
