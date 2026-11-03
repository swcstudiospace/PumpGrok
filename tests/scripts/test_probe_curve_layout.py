"""Curve layout probe never records VERIFIED by itself (INT-10, MKT-03).

A successful ``getAccountInfo`` decode under the ASSUMED layout is a pending review,
``DECODED_PENDING_REVIEW``, in both the JSON record and the doc. Only a human reviewed
doc change may set VERIFIED. The RPC call is stubbed; nothing touches the network.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import struct
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE = REPO_ROOT / "scripts" / "probe_curve_layout.py"

_SPEC = importlib.util.spec_from_file_location("probe_curve_layout", PROBE)
assert _SPEC is not None and _SPEC.loader is not None
probe_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(probe_mod)

ACCOUNT = "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin"
ENDPOINT = "https://api.mainnet-beta.solana.com"
CURVE = struct.Struct("<8sQQQQQB")


def _rpc_payload() -> dict[str, Any]:
    raw = CURVE.pack(
        bytes.fromhex(probe_mod.EXPECTED_DISCRIMINATOR_HEX),
        30_000_000_000,
        1_073_000_000,
        0,
        0,
        1_000_000_000,
        0,
    )
    value = {
        "owner": probe_mod.EXPECTED_PROGRAM_ID,
        "lamports": 2_039_280,
        "executable": False,
        "data": [base64.b64encode(raw).decode("ascii"), "base64"],
    }
    return {"result": {"context": {"slot": 1}, "value": value}}


def test_successful_decode_is_pending_review_not_verified(tmp_path, monkeypatch):
    monkeypatch.setattr(probe_mod, "_rpc_get_account", lambda *_args: _rpc_payload())
    out = tmp_path / "probe.json"
    doc = tmp_path / "CURVE_LAYOUT_PROBE.md"

    rc = probe_mod.main(
        ["--endpoint", ENDPOINT, "--account", ACCOUNT, "--out", str(out), "--doc", str(doc)]
    )

    assert rc == 0
    record = json.loads(out.read_text(encoding="utf-8"))
    doc_text = doc.read_text(encoding="utf-8")
    assert record["layout_status"] != "VERIFIED"
    assert record["layout_status"] == "DECODED_PENDING_REVIEW"
    assert "reviewed_by" not in record
    assert "Status: VERIFIED" not in doc_text
    assert "Status: DECODED_PENDING_REVIEW" in doc_text
