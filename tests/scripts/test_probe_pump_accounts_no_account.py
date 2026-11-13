"""No bonding-curve account configured: the maintained probe refuses before any RPC call.

Retargeted from the retired curve-layout probe test. That probe wrote a doc with a review
paragraph on this path; scripts/probe_pump_accounts.py writes no doc and exits 2 with no
record, so the no-RPC and no-write guarantees are what carry over. Every test injects a
fake fetch and never touches the network.
"""

from __future__ import annotations

import importlib.util
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

ENDPOINT = "https://api.mainnet-beta.solana.com"


class _Fetch:
    """Records every call; the no-account path must never reach it."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, endpoint: str, account: str, timeout: float) -> dict[str, Any] | None:
        self.calls.append((endpoint, account))
        return None


@pytest.mark.parametrize("account_args", [["--account", ""], []], ids=["empty-flag", "unset"])
def test_no_account_configured_makes_no_rpc_call_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, account_args: list[str]
) -> None:
    monkeypatch.delenv("BONDING_CURVE_ACCOUNT", raising=False)
    fetch = _Fetch()
    out = tmp_path / "probe.json"

    rc = probe_mod.main(
        [*account_args, "--endpoint", ENDPOINT, "--out", str(out)],
        fetch=fetch,
        clock=FixtureClock(),
    )

    assert rc == 2
    assert fetch.calls == []
    assert not out.exists()
