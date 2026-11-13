"""ONB-02 and ONB-05: `doctor --json` names each input with its requirement, status and source.

Each record carries exactly name, required_for_mode, status and source. No value ever appears in
stdout or stderr, and a missing required input or a forbidden input present makes doctor exit
nonzero.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pumpgrok.cli.codes import EXIT_CONFIG, EXIT_OK
from pumpgrok.cli.dispatch import main
from pumpgrok.cli.parsing import build_parser
from pumpgrok.cli.verbs_ops import _doctor_verb
from pumpgrok.config.settings import load_settings
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS, roster_tool_names
from pumpgrok.doctor import INPUT_NAMES
from pumpgrok.ledger import operator_choices as oc
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.ledger.store import LedgerStore

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
DEFAULT_RPC = "https://api.mainnet-beta.solana.com"
RECORD_KEYS = {"name", "required_for_mode", "status", "source"}

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


def _records(stdout: str) -> dict[str, dict[str, str]]:
    parsed = json.loads(stdout)
    assert isinstance(parsed, list)
    return {record["name"]: record for record in parsed}


def _record_complete_real_authority() -> None:
    """An explicit RPC choice and an authenticated allow for every roster tool, in the ledger."""
    oc.init_key(oc.OPERATOR_DIR)
    store = LedgerStore(PAPER_LEDGER_PATH)
    try:
        oc.record_rpc_choice(
            store,
            url=DEFAULT_RPC,
            configured_urls=[DEFAULT_RPC],
            operator_dir=oc.OPERATOR_DIR,
            now=NOW,
        )
        for seat in EXPECTED_SEAT_IDS:
            for tool in sorted(roster_tool_names(oc.DEFAULT_CONTRACTS_DIR, seat)):
                oc.record_tool_choice(
                    store,
                    seat=seat,
                    tool=tool,
                    decision="allow",
                    now=NOW,
                    operator_dir=oc.OPERATOR_DIR,
                )
    finally:
        store.close()


def test_cli_parser_accepts_the_doctor_json_flag() -> None:
    parsed = build_parser().parse_args(["doctor", "--json", "--mode", "live"])
    assert (parsed.verb, parsed.json, parsed.mode) == ("doctor", True, "live")
    assert build_parser().parse_args(["doctor"]).json is False


def test_json_has_one_record_per_input_with_exactly_four_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = _doctor_verb(_args("paper"), load_settings(mode="paper"))
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert captured.err == ""
    assert [record["name"] for record in parsed] == list(INPUT_NAMES)
    for record in parsed:
        assert set(record) == RECORD_KEYS
    # A fresh paper install has no authenticated seat decisions, so the paper check fails.
    assert _records(captured.out)["seat_tool_access"]["status"] == "missing"
    assert code == EXIT_CONFIG


def test_live_incomplete_exits_nonzero_and_names_each_missing_required_input(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = _doctor_verb(_args("live"), load_settings(mode="live"))
    records = _records(capsys.readouterr().out)
    assert code == EXIT_CONFIG
    assert records["wallet_public_address"]["status"] == "missing"
    assert records["rpc_endpoint"]["status"] == "missing"
    assert records["seat_tool_access"]["status"] == "missing"
    assert records["hmac_confirmation_key"]["status"] == "absent"


def test_cli_live_json_exits_nonzero_on_an_empty_environment(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["doctor", "--json", "--mode", "live"])
    captured = capsys.readouterr()
    assert code != EXIT_OK
    assert set(_records(captured.out)) == set(INPUT_NAMES)


@pytest.mark.parametrize("mode", ["paper", "live"])
def test_secret_values_never_reach_stdout_or_stderr(
    mode: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    xai_key = "xai-doctor-sentinel-41c9"
    hmac_key = "hmac-doctor-sentinel-08de"
    monkeypatch.setenv("PUMPGROK_GROK_GATEWAY__ENABLED", "true")
    monkeypatch.setenv("PUMPGROK_GROK__API_KEY", xai_key)
    monkeypatch.setenv("PUMPGROK_CONFIRMATION_KEY", hmac_key)
    monkeypatch.setenv("PUMPGROK_WALLET__ALLOWLIST", json.dumps([VALID_ADDRESS]))
    _doctor_verb(_args(mode), load_settings(mode=mode))
    captured = capsys.readouterr()
    for secret in (xai_key, hmac_key, VALID_ADDRESS):
        assert secret not in captured.out
        assert secret not in captured.err


def test_complete_live_authority_exits_zero_and_every_required_input_is_present(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _record_complete_real_authority()
    monkeypatch.setenv("PUMPGROK_WALLET__ALLOWLIST", json.dumps([VALID_ADDRESS]))
    code = _doctor_verb(_args("live"), load_settings(mode="live"))
    captured = capsys.readouterr()
    records = _records(captured.out)
    assert code == EXIT_OK, captured.out
    assert records["wallet_public_address"]["status"] == "present"
    assert records["rpc_endpoint"]["status"] == "present"
    assert records["seat_tool_access"]["status"] == "present"
    assert VALID_ADDRESS not in captured.out
