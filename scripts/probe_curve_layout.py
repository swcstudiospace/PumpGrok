#!/usr/bin/env python3
"""Read-only bonding-curve layout probe (INT-10, R65).

One ``getAccountInfo`` call against the configured public Solana RPC for a
known bonding-curve account, decoded under the ASSUMED layout in
``src/pumpgrok/tools/onchain/curve_layout.py`` (8-byte discriminator, five
little-endian u64 reserve counters, one-byte completion flag).

Read-only by construction: stdlib ``urllib`` POST of a single ``getAccountInfo``
body, no keys loaded, no wallet, no signing path. On success the decoded
layout is written to ``tests/fixtures/rpc/bonding_curve/probe.json`` and
``docs/CURVE_LAYOUT_PROBE.md`` records ``Status: VERIFIED``. On any failure
(unreachable network, unknown account, undecodable bytes) the script exits 0,
keeps ``LAYOUT_STATUS`` ASSUMED, writes ``probe.json`` carrying the exact
error text verbatim, and writes the doc with ``Status: ASSUMED`` plus an
``Error: <exact probe error>`` line. While ASSUMED, RPC-derived prices stay
fail-closed (``data_unavailable``) per the existing rule in ``curve_layout``.

Usage:
    uv run python scripts/probe_curve_layout.py
    uv run python scripts/probe_curve_layout.py --account <pubkey>
    BONDING_CURVE_ACCOUNT=<pubkey> uv run python scripts/probe_curve_layout.py
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import struct
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENDPOINT = "https://api.mainnet-beta.solana.com"
DEFAULT_OUT = REPO_ROOT / "tests" / "fixtures" / "rpc" / "bonding_curve" / "probe.json"
DEFAULT_DOC = REPO_ROOT / "docs" / "CURVE_LAYOUT_PROBE.md"

_CURVE_STRUCT = struct.Struct("<8sQQQQQB")
_EXPECTED_SIZE = _CURVE_STRUCT.size


def _now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rpc_get_account(endpoint: str, account: str, commitment: str, timeout: float) -> dict:
    """Single read-only getAccountInfo; raises on any transport or RPC error."""
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": "curve-layout-probe",
            "method": "getAccountInfo",
            "params": [account, {"encoding": "base64", "commitment": commitment}],
        }
    ).encode("utf-8")
    if not endpoint.startswith("https://"):
        raise ValueError("RPC endpoint must use https")
    request = urllib.request.Request(  # noqa: S310 - scheme checked above
        endpoint, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    if isinstance(payload.get("error"), dict):
        err = payload["error"]
        raise RuntimeError(f"rpc error {err.get('code')}: {err.get('message')}")
    return payload


def _decode_account(raw: bytes) -> dict:
    """Decode raw account bytes under the ASSUMED layout; raises on mismatch."""
    if len(raw) != _EXPECTED_SIZE:
        raise ValueError(f"curve account size {len(raw)} != ASSUMED {_EXPECTED_SIZE}")
    (disc, vsol, vtok, rsol, rtok, supply, complete) = _CURVE_STRUCT.unpack(raw)
    if complete not in (0, 1):
        raise ValueError(f"curve completion flag not boolean: {complete!r}")
    for name, value in (
        ("virtual_sol", vsol),
        ("virtual_token", vtok),
        ("real_sol", rsol),
        ("real_token", rtok),
        ("supply", supply),
    ):
        if value == 0 and name in ("virtual_sol", "virtual_token", "supply"):
            raise ValueError(f"curve reserve {name} is zero; price undefined")
    return {
        "discriminator_hex": disc.hex(),
        "virtual_sol_reserves_lamports": vsol,
        "virtual_token_reserves_units": vtok,  # pragma: allowlist secret: on-chain reserve count
        "real_sol_reserves_lamports": rsol,
        "real_token_reserves_units": rtok,
        "total_supply_units": supply,
        "complete": bool(complete),
    }


def _write_assumed(
    out: Path, doc: Path, *, endpoint: str, account: str | None, commitment: str, error: str
) -> None:
    record = {
        "fixture": "bonding_curve_probe",
        "layout_status": "ASSUMED",
        "endpoint": endpoint,
        "account": account,
        "commitment": commitment,
        "probed_at": _now_utc(),
        "decoded": None,
        "probe_error": error,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(
        "# Bonding-curve layout probe (INT-10, R65)\n"
        "\n"
        "Status: ASSUMED\n"
        f"Error: {error}\n"
        "\n"
        f"Endpoint: {endpoint}\n"
        f"Method: getAccountInfo (read-only, no keys)\n"
        "Layout: ASSUMED until a live probe decodes under it; "
        "RPC-derived entries fail closed with data_unavailable.\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only bonding-curve layout probe.")
    parser.add_argument("--endpoint", default=os.environ.get("RPC_ENDPOINT", DEFAULT_ENDPOINT))
    parser.add_argument("--account", default=os.environ.get("BONDING_CURVE_ACCOUNT", ""))
    parser.add_argument("--commitment", default="confirmed")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--doc", default=str(DEFAULT_DOC))
    args = parser.parse_args(argv)

    out = Path(args.out)
    doc = Path(args.doc)
    account = args.account.strip() or None

    if account is None:
        _write_assumed(
            out,
            doc,
            endpoint=args.endpoint,
            account=None,
            commitment=args.commitment,
            error="no bonding-curve account configured; set BONDING_CURVE_ACCOUNT "
            "or pass --account <pubkey>; no RPC call made; layout stays ASSUMED",
        )
        return 0

    try:
        payload = _rpc_get_account(args.endpoint, account, args.commitment, args.timeout)
        value = (payload.get("result") or {}).get("value")
        if value is None:
            raise ValueError(f"account not found: {account}")
        data = value.get("data")
        if not isinstance(data, list) or len(data) != 2 or data[1] != "base64":
            raise ValueError("curve account is not base64-encoded bytes")
        raw = base64.b64decode(data[0], validate=True)
        decoded = _decode_account(raw)
    except Exception as exc:  # the exact text is the recorded artifact
        _write_assumed(
            out,
            doc,
            endpoint=args.endpoint,
            account=account,
            commitment=args.commitment,
            error=f"{type(exc).__name__}: {exc}",
        )
        return 0

    record = {
        "fixture": "bonding_curve_probe",
        "layout_status": "VERIFIED",
        "endpoint": args.endpoint,
        "account": account,
        "commitment": args.commitment,
        "probed_at": _now_utc(),
        "context_slot": ((payload.get("result") or {}).get("context") or {}).get("slot"),
        "account_len": len(raw),
        "account_sha256": hashlib.sha256(raw).hexdigest(),
        "decoded": decoded,
        "probe_error": None,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(
        "# Bonding-curve layout probe (INT-10, R65)\n"
        "\n"
        "Status: VERIFIED\n"
        "\n"
        f"Endpoint: {args.endpoint}\n"
        f"Account: {account}\n"
        "Method: getAccountInfo (read-only, no keys)\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
