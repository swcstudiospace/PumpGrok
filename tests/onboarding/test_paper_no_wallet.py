"""Paper never reads the wallet field."""

from pumpgrok.onboarding.doctor_report import doctor_records


def test_wallet_is_not_read_in_paper() -> None:
    records = doctor_records({"PUMPGROK_WALLET": "anything"}, "paper")
    by_name = {record.name: record for record in records}
    assert by_name["wallet_public_address"].status == "not-read"


def test_wallet_is_required_in_live() -> None:
    records = doctor_records({}, "live")
    by_name = {record.name: record for record in records}
    assert by_name["wallet_public_address"].required_for_mode
    assert by_name["wallet_public_address"].status == "missing"
