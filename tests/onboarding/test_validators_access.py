"""Onboarding validators, access records and doctor records (ONB-01..ONB-10).

Pure unit checks over tmp files: wallet curve points, host-only RPC choices,
access grants, and the per-mode readiness records the start gate reads.
"""

from __future__ import annotations

from pathlib import Path

from pumpgrok.onboarding.access import (
    enabled_seats_without_access,
    has_access,
    record_access,
)
from pumpgrok.onboarding.doctor_report import doctor_records, failing_records
from pumpgrok.onboarding.inventory import SPEC_BY_NAME, inventory_snapshot_hash
from pumpgrok.onboarding.start_gate import check_start
from pumpgrok.onboarding.validators import (
    _is_curve_point,
    host_only,
    is_valid_wallet_address,
    record_choice_via_text,
    refuse_wallet,
)

# RFC 8032 TEST 1 public key in base58: a real, non-small-order point.
VALID_POINT = "FVen3X669xLzsi6N2V91DoiyzHzg1uAgqiT8jZ9nS96Z"


def test_wallet_address_accepts_a_real_curve_point() -> None:
    assert is_valid_wallet_address(VALID_POINT) is True
    assert refuse_wallet(VALID_POINT) == ""


def test_wallet_address_refuses_non_points() -> None:
    # The onboarding check is a quadratic-residue test (not the strict
    # small-order-aware decoder in config): bad alphabet, empty, and
    # overlong input are refused here; the settings allowlist applies the
    # stricter curve-point check.
    assert is_valid_wallet_address("0" * 44) is False
    assert is_valid_wallet_address("") is False
    assert is_valid_wallet_address("1" * 45) is False
    refusal = refuse_wallet("0" * 44)
    assert "wallet_public_address refused" in refusal
    assert "0000" not in refusal


def test_host_only_drops_path_query_and_userinfo() -> None:
    assert host_only("https://user:secret@rpc.example.org:8443/v1?api-key=x") == (
        "https://rpc.example.org:8443"
    )
    assert host_only("wss://rpc.example.org/ws") == "wss://rpc.example.org"


def test_record_choice_writes_host_only_row(tmp_path: Path) -> None:
    path = tmp_path / "choices.jsonl"
    row = record_choice_via_text(str(path), "rpc_endpoint", "https://rpc.example.org/v1")
    assert row == {
        "name": "rpc_endpoint",
        "value": "https://rpc.example.org",
        "source": "operator-choice",
    }
    assert "rpc.example.org" in path.read_text(encoding="utf-8")


def test_access_grants_are_per_seat(tmp_path: Path) -> None:
    path = tmp_path / "access-decisions.jsonl"
    assert has_access(path, "bot-01-scout") is False
    assert enabled_seats_without_access(path, ("bot-01-scout", "bot-02-risk")) == [
        "bot-01-scout",
        "bot-02-risk",
    ]
    record_access(path, "bot-01-scout")
    assert has_access(path, "bot-01-scout") is True
    assert has_access(path, "bot-02-risk") is False
    assert enabled_seats_without_access(path, ("bot-01-scout", "bot-02-risk")) == ["bot-02-risk"]


def test_doctor_records_report_paper_statuses() -> None:
    records = {record.name: record for record in doctor_records({}, "paper")}
    assert records["xai_api_key"].status == "missing"
    assert records["wallet_public_address"].status == "not-read"
    assert records["rpc_endpoint"].status == "default"
    assert records["seat_tool_access"].status == "missing"
    assert records["hmac_confirmation_key"].status == "missing"
    failing = [record.name for record in failing_records(list(records.values()))]
    assert failing == ["xai_api_key", "seat_tool_access"]


def test_doctor_records_present_key_and_live_forbidden_hmac() -> None:
    env: dict[str, str] = {}
    env[SPEC_BY_NAME["xai_api_key"].source] = "x"
    env[SPEC_BY_NAME["hmac_confirmation_key"].source] = "y"
    records = {record.name: record for record in doctor_records(env, "paper")}
    assert records["xai_api_key"].status == "present"
    assert records["hmac_confirmation_key"].status == "present"
    live = {record.name: record for record in doctor_records(env, "live")}
    assert live["wallet_public_address"].status == "missing"
    assert live["hmac_confirmation_key"].status == "forbidden-present"


def test_check_start_missing_until_seats_granted(tmp_path: Path) -> None:
    access = tmp_path / "access-decisions.jsonl"
    seats = ("bot-01-scout", "bot-02-risk", "bot-06-exit")
    missing = check_start({}, "paper", access_path=access, seats=seats)
    assert "seat_tool_access" in missing
    for seat in seats:
        record_access(access, seat)
    assert "seat_tool_access" not in check_start({}, "paper", access_path=access, seats=seats)


def test_inventory_hash_is_stable() -> None:
    assert inventory_snapshot_hash() == inventory_snapshot_hash()


def test_curve_point_rejects_bad_shapes() -> None:
    assert _is_curve_point(b"\x00" * 31) is False
    assert _is_curve_point(b"\xff" * 32) is False  # y >= field, non-canonical
    rfc_hex = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
    assert _is_curve_point(bytes.fromhex(rfc_hex)) is True
