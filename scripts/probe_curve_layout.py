#!/usr/bin/env python3
"""Read-only bonding-curve layout probe (INT-10, R65).

One ``getAccountInfo`` call against the configured public Solana RPC for a
known bonding-curve account, decoded under the ASSUMED layout in
``src/pumpgrok/tools/onchain/curve_layout.py`` (8-byte discriminator, five
little-endian u64 reserve counters, one-byte completion flag).

Read-only by construction: stdlib ``urllib`` POST of a single ``getAccountInfo``
body, no keys loaded, no wallet, no signing path. On success the decoded
layout is written to ``tests/fixtures/rpc/bonding_curve/probe.json`` and
``docs/CURVE_LAYOUT_PROBE.md`` records ``Status: VERIFIED`` only when the account is owned by the
expected program and carries the expected discriminator. On any failure
(unreachable network, unknown account, undecodable bytes) the script exits 0,
keeps ``LAYOUT_STATUS`` ASSUMED, writes ``probe.json`` carrying the probe error
with credentials redacted, and writes the doc with ``Status: ASSUMED`` plus an
``Error: <redacted probe error>`` line. While ASSUMED, RPC-derived prices stay
fail-closed (``data_unavailable``) per the existing rule in ``curve_layout``.
An endpoint carrying credentials (userinfo or a credential-named query
parameter) is refused with exit 2 before any RPC call or write; only its
scheme, host and path are ever written.

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
import re
import struct
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit, urlunsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENDPOINT = "https://api.mainnet-beta.solana.com"
DEFAULT_OUT = REPO_ROOT / "tests" / "fixtures" / "rpc" / "bonding_curve" / "probe.json"
DEFAULT_DOC = REPO_ROOT / "docs" / "CURVE_LAYOUT_PROBE.md"

_CURVE_STRUCT = struct.Struct("<8sQQQQQB")
_EXPECTED_SIZE = _CURVE_STRUCT.size

# Owner and discriminator a bonding-curve account must carry before its bytes
# are trusted. Both match tests/fixtures/rpc/bonding_curve/layout.json.
EXPECTED_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
EXPECTED_DISCRIMINATOR_HEX = "17b7f83760d8ac60"

# Query-parameter names that carry credentials, matched case-insensitively.
_CREDENTIAL_NAME = re.compile(r"api[-_]?key|token|secret|password|key", re.IGNORECASE)
# The same names as they appear inside free text, e.g. "...?api_key=VALUE".
_CREDENTIAL_ASSIGNMENT = re.compile(
    r"([\w.-]*(?:api[-_]?key|token|secret|password|key)[\w.-]*=)[^\s&#'\"]*", re.IGNORECASE
)
_USERINFO_IN_TEXT = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://)[^\s/?#]*@")


def _require_credential_free(endpoint: str) -> None:
    """Raise unless the endpoint has no userinfo and no credential-named query parameter."""
    try:
        parts = urlsplit(endpoint)
    except ValueError:
        raise ValueError("RPC endpoint is not a parseable URL; URL not echoed") from None
    if "@" in parts.netloc:
        raise ValueError(
            "RPC endpoint carries credentials in its userinfo; URL not echoed; "
            "remove them from --endpoint or RPC_ENDPOINT"
        )
    for name, _ in parse_qsl(parts.query, keep_blank_values=True):
        if _CREDENTIAL_NAME.search(name):
            raise ValueError(
                "RPC endpoint carries a credential-named query parameter; URL not echoed; "
                "remove it from --endpoint or RPC_ENDPOINT"
            )


def _redact_endpoint(endpoint: str) -> str:
    """Keep only scheme, host (with port) and path; drop userinfo, query and fragment."""
    try:
        parts = urlsplit(endpoint)
        port = parts.port
    except ValueError:
        return "<unparseable endpoint>"
    if not parts.scheme or not parts.hostname:
        return "<unparseable endpoint>"
    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    if port is not None:
        host = f"{host}:{port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def _redact_text(text: str, endpoint: str = "") -> str:
    """Scrub error text: no raw endpoint, no userinfo, no credential-named values."""
    if endpoint:
        text = text.replace(endpoint, _redact_endpoint(endpoint))
    text = _USERINFO_IN_TEXT.sub(r"\1REDACTED@", text)
    text = _CREDENTIAL_ASSIGNMENT.sub(r"\1REDACTED", text)
    return " ".join(text.splitlines())


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


def _check_identity(value: dict, raw: bytes) -> None:
    """Raise unless the account is owned by the expected program with its discriminator."""
    owner = value.get("owner")
    if owner != EXPECTED_PROGRAM_ID:
        raise ValueError(f"account owner {owner!r} != expected program {EXPECTED_PROGRAM_ID}")
    disc = raw[:8].hex()
    if disc != EXPECTED_DISCRIMINATOR_HEX:
        raise ValueError(f"account discriminator {disc} != expected {EXPECTED_DISCRIMINATOR_HEX}")


def _write_assumed(
    out: Path, doc: Path, *, endpoint: str, account: str | None, commitment: str, error: str
) -> None:
    safe_endpoint = _redact_endpoint(endpoint)
    safe_error = _redact_text(error, endpoint)
    record = {
        "fixture": "bonding_curve_probe",
        "layout_status": "ASSUMED",
        "endpoint": safe_endpoint,
        "account": account,
        "commitment": commitment,
        "probed_at": _now_utc(),
        "decoded": None,
        "probe_error": safe_error,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(
        "# Bonding-curve layout probe (INT-10, R65)\n"
        "\n"
        "Status: ASSUMED\n"
        f"Error: {safe_error}\n"
        "\n"
        f"Endpoint: {safe_endpoint}\n"
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

    try:
        _require_credential_free(args.endpoint)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

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
        _check_identity(value, raw)
        decoded = _decode_account(raw)
    except Exception as exc:  # the redacted text is the recorded artifact
        _write_assumed(
            out,
            doc,
            endpoint=args.endpoint,
            account=account,
            commitment=args.commitment,
            error=f"{type(exc).__name__}: {exc}",
        )
        return 0

    safe_endpoint = _redact_endpoint(args.endpoint)
    record = {
        "fixture": "bonding_curve_probe",
        "layout_status": "VERIFIED",
        "endpoint": safe_endpoint,
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
        f"Endpoint: {safe_endpoint}\n"
        f"Account: {account}\n"
        "Method: getAccountInfo (read-only, no keys)\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
