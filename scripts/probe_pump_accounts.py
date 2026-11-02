#!/usr/bin/env python3
"""Read-only pump account probe (B02, MKT-03, OD-04).

One ``getAccountInfo`` call for one bonding-curve account on the configured Solana
RPC, decoded under the ASSUMED layout in ``pumpgrok.tools.onchain.curve_layout``.
The only RPC method used is ``getAccountInfo``. No key is loaded and no transaction
is built, so the script has no send path.

The record it writes (default ``var/probe/pump_accounts.json``) never reads VERIFIED.
An account that decodes under the expected owner and discriminator is
``decoded_pending_review``. Every other outcome is ``ASSUMED`` with the exact probe
error. Promoting the layout is a human review step (OD-04), done outside this script.

Exit codes: 0 when a record was written (decoded or ASSUMED); 2 when the account or
endpoint is refused before any RPC call.

Usage:
    uv run python scripts/probe_pump_accounts.py --account <pubkey>
    BONDING_CURVE_ACCOUNT=<pubkey> uv run python scripts/probe_pump_accounts.py
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from pumpgrok.core.ids import Clock
from pumpgrok.replay.clock import WallClock
from pumpgrok.tools.onchain.curve_layout import CurveDecodeError, decode_curve_account

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENDPOINT = "https://api.mainnet-beta.solana.com"
DEFAULT_OUT = REPO_ROOT / "var" / "probe" / "pump_accounts.json"
DEFAULT_TIMEOUT_S = 15.0

# Owner and discriminator a bonding-curve account must carry before its bytes are
# trusted. Both match docs/CURVE_LAYOUT_PROBE.md and scripts/probe_curve_layout.py.
EXPECTED_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
EXPECTED_DISCRIMINATOR_HEX = "17b7f83760d8ac60"

STATUS_DECODED = "decoded_pending_review"
STATUS_ASSUMED = "ASSUMED"

_PUBKEY = re.compile(r"[1-9A-HJ-NP-Za-km-z]{32,44}")
_CREDENTIAL_NAME = re.compile(r"api[-_]?key|token|secret|password|key", re.IGNORECASE)
# A long opaque path segment is a provider key in the URL path, e.g. /v2/<key>.
_OPAQUE_PATH_SEGMENT = re.compile(r"[A-Za-z0-9_-]{20,}")
# Any URL inside free text (an RPC error may echo the endpoint) and any credential assignment.
_URL_IN_TEXT = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://\S+")
_ASSIGNMENT_IN_TEXT = re.compile(r"(?i)(api[-_]?key|token|secret|password|key)=\S*")

AccountFetch = Callable[[str, str, float], Mapping[str, Any] | None]


def _path_has_credential(path: str) -> bool:
    return any(_OPAQUE_PATH_SEGMENT.fullmatch(segment) for segment in path.split("/"))


def _credential_problem(endpoint: str) -> str | None:
    """Why the endpoint must not be used, or None. The URL itself is never echoed."""
    try:
        parts = urlsplit(endpoint)
    except ValueError:
        return "RPC endpoint is not a parseable URL"
    if "@" in parts.netloc:
        return "RPC endpoint carries userinfo credentials"
    if any(
        _CREDENTIAL_NAME.search(name) for name, _ in parse_qsl(parts.query, keep_blank_values=True)
    ):
        return "RPC endpoint carries a credential-named query parameter"
    if _path_has_credential(parts.path):
        return "RPC endpoint carries a credential in its URL path"
    return None


def redact_endpoint(endpoint: str) -> str:
    """Keep only scheme, host, port and path; a credential-bearing path is a placeholder."""
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
    path = "/<redacted>" if _path_has_credential(parts.path) else parts.path
    return urlunsplit((parts.scheme, host, path, "", ""))


class RpcFailure(RuntimeError):
    """A JSON-RPC error or malformed reply: the code and a sanitized message, never the URL."""

    def __init__(self, code: int | None, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _sanitize_message(message: object, endpoint: str) -> str:
    """Make an RPC message safe to record: no URL, no credential value, ASCII, short."""
    text = "" if message is None else str(message)
    if endpoint:
        text = text.replace(endpoint, "<url redacted>")
    text = _URL_IN_TEXT.sub("<url redacted>", text)
    text = _ASSIGNMENT_IN_TEXT.sub(lambda m: f"{m.group(1)}=REDACTED", text)
    text = "".join(ch if 32 <= ord(ch) < 127 else " " for ch in text)
    return " ".join(text.split())[:200]


def _rpc_error_text(code: int | None, message: str) -> str:
    return f"RPC error {code}: {message}" if code is not None else f"RPC error: {message}"


def fetch_account(endpoint: str, account: str, timeout: float) -> Mapping[str, Any] | None:
    """One read-only getAccountInfo call; returns the ``value`` member, None when absent."""
    if not endpoint.startswith("https://"):
        raise ValueError("RPC endpoint must use https")
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": "pump-accounts-probe",
            "method": "getAccountInfo",
            "params": [account, {"encoding": "base64", "commitment": "confirmed"}],
        }
    ).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310 - https scheme checked above
        endpoint, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RpcFailure(None, "reply is not a JSON object")
    if "error" in payload:
        err = payload["error"]
        if isinstance(err, dict):
            code = err.get("code")
            raise RpcFailure(
                code if isinstance(code, int) else None,
                _sanitize_message(err.get("message"), endpoint),
            )
        raise RpcFailure(None, _sanitize_message(err, endpoint))
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RpcFailure(None, "result is not a JSON object")
    value = result.get("value")
    if value is None or isinstance(value, dict):
        return value
    raise RpcFailure(None, "account value is not a JSON object")


def _raw_bytes(value: Mapping[str, Any]) -> bytes | None:
    data = value.get("data")
    if not (isinstance(data, list) and len(data) == 2 and data[1] == "base64"):
        return None
    if not isinstance(data[0], str):
        return None
    try:
        return base64.b64decode(data[0], validate=True)
    except ValueError:
        return None


def _decode_outcome(value: Mapping[str, Any] | None) -> tuple[str | None, dict[str, Any] | None]:
    """Return ``(error, decoded)``; ``error`` is None only when the account decodes."""
    if value is None:
        return "account not found; layout stays ASSUMED", None
    if value.get("owner") != EXPECTED_PROGRAM_ID:
        return "owner is not the expected program; layout stays ASSUMED", None
    raw = _raw_bytes(value)
    if raw is None:
        return "account data is not base64; layout stays ASSUMED", None
    try:
        state = decode_curve_account(raw)
    except CurveDecodeError as exc:
        return f"{exc}; layout stays ASSUMED", None
    if raw[:8].hex() != EXPECTED_DISCRIMINATOR_HEX:
        return "discriminator does not match the ASSUMED layout; layout stays ASSUMED", None
    return None, state.model_dump()


def probe_account(account: str, endpoint: str, fetch: AccountFetch, clock: Clock) -> dict[str, Any]:
    """Probe one account and return its record. A probe failure is a record, never a raise."""
    record: dict[str, Any] = {
        "probe": "pump_accounts",
        "account": account,
        "endpoint": redact_endpoint(endpoint),
        "captured_at": clock.utc_iso(),
        "status": STATUS_ASSUMED,
        "error": None,
        "decoded": None,
    }
    try:
        value = fetch(endpoint, account, DEFAULT_TIMEOUT_S)
    except RpcFailure as exc:
        record["error"] = f"{_rpc_error_text(exc.code, exc.message)}; layout stays ASSUMED"
        return record
    except urllib.error.HTTPError as exc:
        record["error"] = (
            f"RPC request failed (HTTP {exc.code}); endpoint not echoed; layout stays ASSUMED"
        )
        return record
    except Exception as exc:  # any other transport failure: class name only, never its text
        record["error"] = (
            f"RPC request failed ({type(exc).__name__}); endpoint not echoed; layout stays ASSUMED"
        )
        return record
    error, decoded = _decode_outcome(value)
    if error is not None:
        record["error"] = error
        return record
    record["status"] = STATUS_DECODED
    record["decoded"] = decoded
    return record


def main(
    argv: list[str] | None = None,
    *,
    fetch: AccountFetch = fetch_account,
    clock: Clock | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Read-only pump account probe (B02, MKT-03).")
    parser.add_argument("--account", default=os.environ.get("BONDING_CURVE_ACCOUNT", ""))
    parser.add_argument("--endpoint", default=os.environ.get("RPC_ENDPOINT", DEFAULT_ENDPOINT))
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    if not _PUBKEY.fullmatch(args.account):
        print(
            "refused: --account must be a base58 public key "
            "(set --account or BONDING_CURVE_ACCOUNT)",
            file=sys.stderr,
        )
        return 2
    problem = _credential_problem(args.endpoint)
    if problem is not None:
        print(
            f"refused: {problem}; URL not echoed; remove the credential from --endpoint "
            "or RPC_ENDPOINT",
            file=sys.stderr,
        )
        return 2
    record = probe_account(
        args.account, args.endpoint, fetch, clock if clock is not None else WallClock()
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"probe status={record['status']} record={args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
