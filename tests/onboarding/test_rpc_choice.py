"""RPC choice records host only; default is never a choice."""

from pathlib import Path

from pumpgrok.onboarding.choices import read_choices, record_choice
from pumpgrok.onboarding.doctor_report import doctor_records
from pumpgrok.onboarding.validators import host_only


def test_host_only_strips_path_query_userinfo_key() -> None:
    assert (
        host_only("https://user:secret@api.mainnet-beta.solana.com:8443/v2?key=1")
        == "https://api.mainnet-beta.solana.com:8443"
    )


def test_default_is_not_a_choice() -> None:
    records = doctor_records({}, "paper")
    by_name = {record.name: record for record in records}
    assert by_name["rpc_endpoint"].status == "default"


def test_recorded_choice_is_host_only(tmp_path: Path) -> None:
    path = tmp_path / "choices.jsonl"
    record_choice(path, "rpc_endpoint", "https://user:pw@example.com:9000/path?x=1")
    rows = read_choices(path)
    assert len(rows) == 1
    assert rows[0]["value"] == "https://example.com:9000"
    assert "pw" not in rows[0]["value"]
    assert "path" not in rows[0]["value"]
