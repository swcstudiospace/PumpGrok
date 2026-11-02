"""Read-only pump account probe (B02, MKT-03, OD-04).

``scripts/probe_pump_accounts.py`` reads one bonding-curve account with a single
``getAccountInfo`` call and records what it decoded. It has no send, sign or airdrop
path, and its record never reads VERIFIED: a decoded account is
``decoded_pending_review`` and every other outcome is ASSUMED with the exact probe
error. Only a human reviewer may flip the layout (OD-04), outside this script.

Every test injects a fake fetch and a virtual clock. None touches the network.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import struct
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
ENDPOINT = "https://api.mainnet-beta.solana.com"
PROGRAM = probe_mod.EXPECTED_PROGRAM_ID
DISCRIMINATOR = bytes.fromhex(probe_mod.EXPECTED_DISCRIMINATOR_HEX)
CURVE = struct.Struct("<8sQQQQQB")

FORBIDDEN_SEND_TOKENS = ("sendTransaction", "send_transaction", "requestAirdrop", "signTransaction")


def _account_value(*, owner: str = PROGRAM, disc: bytes = DISCRIMINATOR) -> dict[str, Any]:
    raw = CURVE.pack(disc, 30_000_000_000, 1_073_000_000, 0, 0, 1_000_000_000, 0)
    return {
        "owner": owner,
        "lamports": 2_039_280,
        "executable": False,
        "data": [base64.b64encode(raw).decode("ascii"), "base64"],
    }


class _Fetch:
    """Records calls and returns a canned account value (or raises)."""

    def __init__(self, value: dict[str, Any] | None = None, exc: BaseException | None = None):
        self.value = value
        self.exc = exc
        self.calls: list[tuple[str, str]] = []

    def __call__(self, endpoint: str, account: str, timeout: float) -> dict[str, Any] | None:
        self.calls.append((endpoint, account))
        if self.exc is not None:
            raise self.exc
        return self.value


def test_script_has_no_send_path() -> None:
    text = PROBE.read_text(encoding="utf-8")
    for token in FORBIDDEN_SEND_TOKENS:
        assert token not in text, token
    assert text.isascii()


def test_decoded_account_is_decoded_pending_review_never_verified() -> None:
    fetch = _Fetch(_account_value())
    record = probe_mod.probe_account(ACCOUNT, ENDPOINT, fetch, FixtureClock(start=1.0))
    assert record["status"] == "decoded_pending_review"
    assert record["error"] is None
    assert record["decoded"]["virtual_sol_reserves_lamports"] == 30_000_000_000
    assert record["decoded"]["complete"] is False
    assert "VERIFIED" not in json.dumps(record)
    assert fetch.calls == [(ENDPOINT, ACCOUNT)]


def test_owner_mismatch_stays_assumed_with_exact_error() -> None:
    fetch = _Fetch(_account_value(owner="11111111111111111111111111111111"))
    record = probe_mod.probe_account(ACCOUNT, ENDPOINT, fetch, FixtureClock())
    assert record["status"] == "ASSUMED"
    assert record["error"] == "owner is not the expected program; layout stays ASSUMED"
    assert record["decoded"] is None


def test_discriminator_mismatch_stays_assumed() -> None:
    fetch = _Fetch(_account_value(disc=b"\x00" * 8))
    record = probe_mod.probe_account(ACCOUNT, ENDPOINT, fetch, FixtureClock())
    assert record["status"] == "ASSUMED"
    assert record["error"] == (
        "discriminator does not match the ASSUMED layout; layout stays ASSUMED"
    )


def test_missing_account_stays_assumed() -> None:
    record = probe_mod.probe_account(ACCOUNT, ENDPOINT, _Fetch(None), FixtureClock())
    assert record["status"] == "ASSUMED"
    assert record["error"] == "account not found; layout stays ASSUMED"


def test_transport_failure_is_assumed_and_never_echoes_the_endpoint() -> None:
    secret_url = "https://user:hunter2@rpc.example.test/?api-key=TOPSECRET"
    fetch = _Fetch(exc=OSError(f"connect failed for {secret_url}"))
    record = probe_mod.probe_account(ACCOUNT, secret_url, fetch, FixtureClock())
    assert record["status"] == "ASSUMED"
    assert record["error"].startswith("RPC request failed")
    text = json.dumps(record)
    assert "hunter2" not in text
    assert "TOPSECRET" not in text


def test_main_writes_only_the_out_path_and_exits_zero(tmp_path: Path) -> None:
    out = tmp_path / "probe.json"
    fetch = _Fetch(_account_value())
    rc = probe_mod.main(
        ["--account", ACCOUNT, "--endpoint", ENDPOINT, "--out", str(out)],
        fetch=fetch,
        clock=FixtureClock(),
    )
    assert rc == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["status"] == "decoded_pending_review"
    assert len(fetch.calls) == 1


def test_main_failure_exits_zero_with_assumed_record(tmp_path: Path) -> None:
    out = tmp_path / "probe.json"
    rc = probe_mod.main(
        ["--account", ACCOUNT, "--endpoint", ENDPOINT, "--out", str(out)],
        fetch=_Fetch(exc=TimeoutError("slow")),
        clock=FixtureClock(),
    )
    assert rc == 0
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == "ASSUMED"


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://user:pw@rpc.example.test/",
        "https://rpc.example.test/?api-key=SECRETVALUE",
        "https://rpc.example.test/v2/SECRETPATHKEY1234567890",
    ],
)
def test_credential_endpoint_refused_before_any_call(endpoint: str, tmp_path: Path) -> None:
    out = tmp_path / "probe.json"
    fetch = _Fetch(_account_value())
    rc = probe_mod.main(
        ["--account", ACCOUNT, "--endpoint", endpoint, "--out", str(out)],
        fetch=fetch,
        clock=FixtureClock(),
    )
    assert rc == 2
    assert fetch.calls == []
    assert not out.exists()


def test_invalid_account_is_refused_before_any_call(tmp_path: Path) -> None:
    fetch = _Fetch(_account_value())
    rc = probe_mod.main(
        ["--account", "not-a-pubkey!", "--endpoint", ENDPOINT, "--out", str(tmp_path / "p.json")],
        fetch=fetch,
        clock=FixtureClock(),
    )
    assert rc == 2
    assert fetch.calls == []
