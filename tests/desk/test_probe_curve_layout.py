"""Offline regression tests for the assumed bonding-curve probe layout."""

from __future__ import annotations

import base64
import importlib.util
import json
import struct
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE = REPO_ROOT / "scripts" / "probe_curve_layout.py"
_SPEC = importlib.util.spec_from_file_location("probe_curve_layout", PROBE)
assert _SPEC is not None and _SPEC.loader is not None
probe_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(probe_mod)

# Official base layout: token before SOL for both virtual and real reserves.
DISCRIMINATOR = bytes.fromhex("17b7f83760d8ac60")
BASE_ACCOUNT = struct.pack("<8sQQQQQB", DISCRIMINATOR, 101, 202, 303, 404, 505, 1)
EXPECTED = {
    "discriminator_hex": DISCRIMINATOR.hex(),
    "virtual_token_reserves_units": 101,
    "virtual_sol_reserves_lamports": 202,
    "real_token_reserves_units": 303,
    "real_sol_reserves_lamports": 404,
    "total_supply_units": 505,
    "complete": True,
}


@pytest.mark.parametrize("extension", [b"", bytes(range(117))], ids=["base-49", "extended-166"])
def test_decode_account_uses_token_first_base_prefix(extension: bytes) -> None:
    raw = BASE_ACCOUNT + extension
    assert len(raw) == 49 + len(extension)
    assert probe_mod._decode_account(raw) == EXPECTED


@pytest.mark.parametrize("extension", [b"", bytes(range(117))], ids=["base-49", "extended-166"])
def test_offline_probe_remains_pending_human_review(
    extension: bytes, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    raw = BASE_ACCOUNT + extension
    payload = {
        "result": {
            "context": {"slot": 123},
            "value": {
                "owner": probe_mod.EXPECTED_PROGRAM_ID,
                "data": [base64.b64encode(raw).decode("ascii"), "base64"],
            },
        }
    }
    monkeypatch.setattr(probe_mod, "_rpc_get_account", lambda *_args: payload)
    out = tmp_path / "probe.json"
    doc = tmp_path / "probe.md"

    assert probe_mod.main(
        [
            "--endpoint",
            "https://rpc.example.test",
            "--account",
            "offline-account",
            "--out",
            str(out),
            "--doc",
            str(doc),
        ]
    ) == 0
    record = json.loads(out.read_text(encoding="utf-8"))
    assert record["layout_status"] == "DECODED_PENDING_REVIEW"
    assert record["decoded"] == EXPECTED
    assert record["account_len"] == len(raw)
    assert "Status: DECODED_PENDING_REVIEW" in doc.read_text(encoding="utf-8")
