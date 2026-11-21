"""Empty x.ai key counts as missing; no empty-bearer request is sent."""

from pumpgrok.onboarding.doctor_report import doctor_records, failing_records


def test_empty_key_is_missing() -> None:
    records = doctor_records({"PUMPGROK_GROK__API_KEY": ""}, "paper")
    by_name = {record.name: record for record in records}
    assert by_name["xai_api_key"].status == "missing"
    assert failing_records(records)


def test_present_key_satisfies() -> None:
    records = doctor_records({"PUMPGROK_GROK__API_KEY": "x"}, "paper")
    by_name = {record.name: record for record in records}
    assert by_name["xai_api_key"].status == "present"
