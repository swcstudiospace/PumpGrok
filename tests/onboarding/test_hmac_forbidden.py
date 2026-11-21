"""HMAC confirmation key is forbidden in live."""

from pumpgrok.onboarding.doctor_report import doctor_records, failing_records


def test_present_key_fails_live() -> None:
    records = doctor_records({"PUMPGROK_CONFIRMATION_KEY": "x"}, "live")
    by_name = {record.name: record for record in records}
    assert by_name["hmac_confirmation_key"].status == "forbidden-present"
    assert failing_records(records)


def test_absent_key_in_paper_is_optional() -> None:
    records = doctor_records({}, "paper")
    by_name = {record.name: record for record in records}
    assert by_name["hmac_confirmation_key"].status == "missing"
    assert by_name["hmac_confirmation_key"].required_for_mode is False
