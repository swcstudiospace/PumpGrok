"""INT-10 bonding-curve probe: --discover filter, 429 backoff, and two-layout decode.

No network: every RPC is a stub. These tests pin the decision logic only. They do not check
the on-chain layout; that needs a real account, recorded by the probe itself.
"""

from __future__ import annotations

import email.message
import importlib.util
import struct
import sys
import urllib.error
from pathlib import Path

import pytest

PROBE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "probe_curve_layout.py"
PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
DISC = bytes.fromhex("17b7f83760d8ac60")


def _load():
    spec = importlib.util.spec_from_file_location("probe_curve_layout", PROBE_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["probe_curve_layout"] = mod
    spec.loader.exec_module(mod)
    return mod


probe = _load()

IDL = ["vtok", "vsol", "rtok", "rsol", "supply", "complete"]
REPO = ["vsol", "vtok", "rsol", "rtok", "supply", "complete"]
# Realistic curve scale: token reserves ~1e15 units, SOL reserves ~3e10 lamports, real <= virtual.
VALUES = {
    "vtok": 1_073_000_000_000_000,
    "vsol": 30_000_000_000,
    "rtok": 793_000_000_000_000,
    "rsol": 5_000_000_000,
    "supply": 1_000_000_000_000_000,
}


def _account_bytes(order: list[str], values: dict[str, int], complete: int = 0) -> bytes:
    """Discriminator, then five u64 reserves packed in `order`, then one completion byte."""
    body = b"".join(struct.pack("<Q", values[name]) for name in order if name != "complete")
    return DISC + body + bytes([complete])


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x", code, "err", email.message.Message(), None)


# ---- filter -------------------------------------------------------------------------------


def test_filter_keeps_program_owned_curve_accounts_of_49_bytes_or_more():
    good = {"owner": PROGRAM, "raw": _account_bytes(REPO, VALUES)}
    live = {"owner": PROGRAM, "raw": good["raw"] + b"\x00" * 117}  # observed live length 166
    wrong_owner = {"owner": "11111111111111111111111111111111", "raw": _account_bytes(REPO, VALUES)}
    too_short = {"owner": PROGRAM, "raw": good["raw"][:-1]}
    wrong_disc = {"owner": PROGRAM, "raw": b"\x00" * 8 + good["raw"][8:]}
    kept = probe.filter_curve_candidates([wrong_owner, too_short, wrong_disc, good, live])
    assert kept == [good, live]


# ---- backoff on 429 -----------------------------------------------------------------------


def test_rpc_429_is_retried_with_increasing_backoff_then_succeeds():
    calls = {"n": 0}
    sleeps: list[float] = []

    def stub(method: str, params: list) -> dict:
        calls["n"] += 1
        if calls["n"] <= 2:
            raise _http_error(429)
        return {"context": {"slot": 1}, "value": None}

    result = probe.call_with_backoff(stub, "getAccountInfo", [], sleep=sleeps.append, max_retries=5)
    assert result == {"context": {"slot": 1}, "value": None}
    assert calls["n"] == 3
    assert len(sleeps) == 2 and sleeps[1] > sleeps[0] > 0


def test_non_429_http_error_is_not_retried():
    sleeps: list[float] = []

    def stub(method: str, params: list) -> dict:
        raise _http_error(500)

    with pytest.raises(urllib.error.HTTPError):
        probe.call_with_backoff(stub, "getAccountInfo", [], sleep=sleeps.append, max_retries=5)
    assert sleeps == []


# ---- two-layout decode: order-sensitive invariants ----------------------------------------


def test_exactly_one_layout_passes_when_bytes_are_repo_order():
    verdict = probe.evaluate_layouts(_account_bytes(REPO, VALUES, complete=0))
    assert verdict["passing"] == ["repo_order"]
    assert verdict["flip_allowed"] is True


def test_exactly_one_layout_passes_when_bytes_are_idl_order():
    verdict = probe.evaluate_layouts(_account_bytes(IDL, VALUES, complete=1))
    assert verdict["passing"] == ["idl_order"]
    assert verdict["flip_allowed"] is True


def test_swapped_order_bytes_do_not_verify_as_repo_order():
    # Packed in IDL order, read as repo order: the token and SOL fields swap, so the token
    # scale check rejects the repo reading. Only the IDL reading may pass.
    verdict = probe.evaluate_layouts(_account_bytes(IDL, VALUES, complete=0))
    assert "repo_order" not in verdict["passing"]
    assert verdict["passing"] == ["idl_order"]


def test_all_equal_reserves_cannot_flip_because_they_fail_the_scale_check():
    # Every field equal to 7 reads the same under both orders, but 7 is far below the token and
    # SOL scale bounds. The scale invariant rejects both orders, so neither passes and
    # flip_allowed stays False: a tie is never read as a verdict.
    same = dict.fromkeys(VALUES, 7)
    verdict = probe.evaluate_layouts(_account_bytes(REPO, same, complete=0))
    assert verdict["passing"] == []
    assert verdict["flip_allowed"] is False


def test_real_reserve_above_virtual_is_rejected_under_any_order():
    bad = dict(VALUES, rtok=VALUES["vtok"] * 2)
    verdict = probe.evaluate_layouts(_account_bytes(REPO, bad, complete=0))
    assert verdict["flip_allowed"] is False
    assert "repo_order" not in verdict["passing"]


def test_completion_byte_that_is_not_boolean_is_rejected():
    raw = bytearray(_account_bytes(REPO, VALUES, complete=0))
    raw[-1] = 2
    verdict = probe.evaluate_layouts(bytes(raw))
    assert verdict["flip_allowed"] is False
    assert verdict["passing"] == []


def test_live_length_account_decodes_from_its_49_byte_prefix():
    # Live accounts are 166 bytes; the curve fields are the prefix, trailing bytes are ignored.
    live = _account_bytes(IDL, VALUES, complete=0) + b"\x00" * 117
    verdict = probe.evaluate_layouts(live)
    assert verdict["passing"] == ["idl_order"]
    assert verdict["flip_allowed"] is True
