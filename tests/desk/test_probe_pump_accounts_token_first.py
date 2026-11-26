"""Offline token-first layout tests for the maintained read-only pump probe.

Migrated from the retired curve layout probe (plan 14-09). The tests now
drive ``scripts/probe_pump_accounts.py`` with a stubbed RPC fetch and a fixed clock, so
nothing touches the network.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import struct
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.replay.clock import FixtureClock

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE = REPO_ROOT / "scripts" / "probe_pump_accounts.py"
_SPEC = importlib.util.spec_from_file_location("probe_pump_accounts", PROBE)
assert _SPEC is not None and _SPEC.loader is not None
probe_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(probe_mod)

ACCOUNT = "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin"
ENDPOINT = "https://rpc.example.test"

# Official base layout: token before SOL for both virtual and real reserves.
DISCRIMINATOR = bytes.fromhex("17b7f83760d8ac60")
BASE_ACCOUNT = struct.pack("<8sQQQQQB", DISCRIMINATOR, 101, 202, 303, 404, 505, 1)
EXPECTED_DECODED = {
    "virtual_token_reserves_units": 101,  # pragma: allowlist secret: reserve field name, not a credential
    "virtual_sol_reserves_lamports": 202,
    "real_token_reserves_units": 303,
    "real_sol_reserves_lamports": 404,
    "total_supply_units": 505,
    "complete": True,
}


def _value(raw: bytes) -> dict[str, Any]:
    return {
        "owner": probe_mod.EXPECTED_PROGRAM_ID,
        "lamports": 2_039_280,
        "executable": False,
        "data": [base64.b64encode(raw).decode("ascii"), "base64"],
    }


def _fetch_returning(value: dict[str, Any]) -> Callable[[str, str, float], dict[str, Any]]:
    def fetch(endpoint: str, account: str, timeout: float) -> dict[str, Any]:
        return value

    return fetch


def test_discriminator_gate_matches_official_layout() -> None:
    assert DISCRIMINATOR.hex() == probe_mod.EXPECTED_DISCRIMINATOR_HEX


def test_base_49_account_decodes_token_first() -> None:
    assert len(BASE_ACCOUNT) == 49
    record = probe_mod.probe_account(
        ACCOUNT, ENDPOINT, _fetch_returning(_value(BASE_ACCOUNT)), FixtureClock()
    )
    assert record["error"] is None
    assert record["status"] == probe_mod.STATUS_DECODED
    assert record["decoded"] == EXPECTED_DECODED


def test_extended_166_account_stays_assumed_fail_closed() -> None:
    raw = BASE_ACCOUNT + bytes(range(117))
    assert len(raw) == 166
    record = probe_mod.probe_account(
        ACCOUNT, ENDPOINT, _fetch_returning(_value(raw)), FixtureClock()
    )
    assert record["status"] == probe_mod.STATUS_ASSUMED
    assert record["decoded"] is None
    assert "166-byte extended curve layout is ASSUMED" in record["error"]
    assert record["error"].endswith("layout stays ASSUMED")


@pytest.mark.parametrize(
    ("extension", "status", "decoded"),
    [
        (b"", probe_mod.STATUS_DECODED, EXPECTED_DECODED),
        (bytes(range(117)), probe_mod.STATUS_ASSUMED, None),
    ],
    ids=["base-49", "extended-166-refused"],
)
def test_offline_main_record_is_pending_review_never_verified(
    extension: bytes, status: str, decoded: dict[str, Any] | None, tmp_path: Path
) -> None:
    out = tmp_path / "probe.json"
    rc = probe_mod.main(
        ["--endpoint", ENDPOINT, "--account", ACCOUNT, "--out", str(out)],
        fetch=_fetch_returning(_value(BASE_ACCOUNT + extension)),
        clock=FixtureClock(),
    )
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    record = json.loads(text)
    assert record["status"] == status
    assert record["decoded"] == decoded
    assert "reviewed_by" not in record
    assert "VERIFIED" not in text
