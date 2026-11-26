<<<<<<< HEAD
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
=======
"""ONB-10: in a live desk environment the HMAC confirmation key is forbidden.

Doctor reports the key present or absent by name and source only. A present key fails the live
onboarding check, while every other required input is complete. Paper treats the key as optional.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.cli.codes import EXIT_CONFIG, EXIT_OK
from pumpgrok.cli.verbs_ops import _doctor_verb
from pumpgrok.config.settings import load_settings
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS, roster_tool_names
from pumpgrok.doctor import failing_inputs, input_inventory
from pumpgrok.ledger import operator_choices as oc

HMAC_NAME = "hmac_confirmation_key"
HMAC_SENTINEL = "hmac-forbidden-sentinel-93b2"
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
# RFC 8032 section 7.1, TEST 1 public key: a valid Ed25519 point.
RFC8032_TEST1_PUBLIC = bytes.fromhex(
    "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
)


def _b58encode(raw: bytes) -> str:
    number = int.from_bytes(raw, "big")
    digits = ""
    while number:
        number, remainder = divmod(number, 58)
        digits = _B58[remainder] + digits
    leading_zeros = len(raw) - len(raw.lstrip(b"\x00"))
    return "1" * leading_zeros + digits


VALID_ADDRESS = _b58encode(RFC8032_TEST1_PUBLIC)


@pytest.fixture(autouse=True)
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Own working directory and a PUMPGROK_*-free environment for every test."""
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.startswith("PUMPGROK_"):
            monkeypatch.delenv(name)
    return tmp_path


def _args(mode: str) -> argparse.Namespace:
    return argparse.Namespace(verb="doctor", mode=mode, json=True)


def _complete_live_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every other live input complete: wallet, explicit RPC and every roster tool decided."""
    endpoint = oc.Endpoint("https", "api.mainnet-beta.solana.com", 443)
    monkeypatch.setattr(oc, "rpc_status", lambda *_a, **_k: ("explicit", endpoint))
    decisions: dict[str, Any] = {}
    for seat in EXPECTED_SEAT_IDS:
        for tool in roster_tool_names(oc.DEFAULT_CONTRACTS_DIR, seat):
            scope = oc.tool_scope(seat, tool)
            decisions[scope] = oc.Decision(
                scope=scope,
                decision="allow",
                by="human:operator",
                digest="digest",
                idempotency_key="key",
                payload={},
                bound=True,
            )
    monkeypatch.setattr(oc, "read_authority", lambda *_a, **_k: decisions)
    monkeypatch.setenv("PUMPGROK_WALLET__ALLOWLIST", json.dumps([VALID_ADDRESS]))


def test_live_hmac_is_forbidden_and_reported_by_name_and_source_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PUMPGROK_CONFIRMATION_KEY", HMAC_SENTINEL)
    records = input_inventory(load_settings(mode="live"), "live")
    record = next(item for item in records if item.name == HMAC_NAME)
    assert (record.required_for_mode, record.status, record.source) == (
        "forbidden",
        "present",
        "env",
    )
    assert record in failing_inputs(records)
    assert HMAC_SENTINEL not in repr(records)


def test_absent_live_hmac_is_not_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _complete_live_state(monkeypatch)
    records = input_inventory(load_settings(mode="live"), "live")
    record = next(item for item in records if item.name == HMAC_NAME)
    assert (record.required_for_mode, record.status, record.source) == (
        "forbidden",
        "absent",
        "none",
    )
    assert failing_inputs(records) == []


def test_present_live_hmac_fails_an_otherwise_complete_live_check(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _complete_live_state(monkeypatch)
    monkeypatch.setenv("PUMPGROK_CONFIRMATION_KEY", HMAC_SENTINEL)
    code = _doctor_verb(_args("live"), load_settings(mode="live"))
    captured = capsys.readouterr()
    assert code == EXIT_CONFIG
    names = [record["name"] for record in json.loads(captured.out) if record["status"] == "present"]
    assert HMAC_NAME in names
    assert HMAC_SENTINEL not in captured.out
    assert HMAC_SENTINEL not in captured.err


def test_present_paper_hmac_is_optional_and_does_not_fail_paper(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _complete_live_state(monkeypatch)
    monkeypatch.setenv("PUMPGROK_CONFIRMATION_KEY", HMAC_SENTINEL)
    records = input_inventory(load_settings(mode="paper"), "paper")
    record = next(item for item in records if item.name == HMAC_NAME)
    assert (record.required_for_mode, record.status) == ("optional", "present")
    assert failing_inputs(records) == []
    code = _doctor_verb(_args("paper"), load_settings(mode="paper"))
    captured = capsys.readouterr()
    assert code == EXIT_OK, captured.out
    assert HMAC_SENTINEL not in captured.out
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
