"""Wallet allowlist and notional cap feed live gate rows 5 and 6 (R21, fail closed).

Rows 5 and 6 read the allowlist and the cap the caller passes in; both default to
unmet. Rows 8 and 9 stay unmet in every case: no live adapter ships and no halt or
kill-switch state is readable in this release.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pumpgrok.config.settings import WalletSettings
from pumpgrok.core.units import LAMPORTS_PER_SOL
from pumpgrok.execution.live.live_gate import PRECONDITION_IDS, LiveGate, Precondition

NOW = "2026-10-20T00:00:00Z"
SYSTEM_PROGRAM = "11111111111111111111111111111111"
ALLOWLIST_EMPTY = "live.wallet_allowlist is empty; no public key is allowlisted"
CAP_UNSET = "live.notional_cap_lamports is not set"
CAP_RANGE = "live.notional_cap_lamports must satisfy 0 < value <= 1 SOL"
ADAPTER_UNMET = "no live adapter implementation ships in this release"
HALT_UNMET = "halt, kill switch and breaker state are not readable in this release"


def _by_id(gate: LiveGate) -> dict[str, Precondition]:
    return {item.id: item for item in gate.evaluate(now=NOW)}


def test_default_gate_keeps_all_nine_unmet(tmp_path: Path) -> None:
    """Default settings: rows 5 and 6 fail closed with their unset reasons."""
    rows = LiveGate(mode="live", environ={}, root=tmp_path).evaluate(now=NOW)
    assert tuple(item.id for item in rows) == PRECONDITION_IDS
    assert all(item.met is False for item in rows)
    by_id = {item.id: item for item in rows}
    assert by_id["wallet_allowlist"].reason == ALLOWLIST_EMPTY
    assert by_id["notional_cap"].reason == CAP_UNSET


def test_allowlist_of_one_key_meets_row_5_only(tmp_path: Path) -> None:
    """One 32-byte public key meets row 5; rows 1 to 4, 7, 8 and 9 do not change."""
    assert WalletSettings(allowlist=(SYSTEM_PROGRAM,)).allowlist == (SYSTEM_PROGRAM,)
    baseline = _by_id(LiveGate(mode="live", environ={}, root=tmp_path))
    gate = _by_id(
        LiveGate(
            mode="live",
            environ={},
            root=tmp_path,
            wallet_allowlist=(SYSTEM_PROGRAM,),
        )
    )
    assert gate["wallet_allowlist"].met is True
    assert gate["wallet_allowlist"].reason == "live.wallet_allowlist lists 1 public key(s)"
    assert gate["notional_cap"].met is False
    for name in (
        "mode_live",
        "live_enable_env",
        "min_paper_days",
        "performance_thresholds",
        "confirmation_record",
        "adapter_registered",
        "no_active_stop",
    ):
        assert gate[name] == baseline[name], name


def test_cap_of_one_sol_meets_row_6(tmp_path: Path) -> None:
    """A cap equal to LAMPORTS_PER_SOL is the ceiling and is accepted."""
    gate = _by_id(
        LiveGate(
            mode="live",
            environ={},
            root=tmp_path,
            notional_cap_lamports=LAMPORTS_PER_SOL,
        )
    )
    assert gate["notional_cap"].met is True
    assert gate["notional_cap"].reason == (
        f"live.notional_cap_lamports is {LAMPORTS_PER_SOL} (ceiling 1 SOL)"
    )
    assert gate["wallet_allowlist"].met is False


@pytest.mark.parametrize("cap", [0, LAMPORTS_PER_SOL + 1])
def test_out_of_range_cap_leaves_row_6_unmet(tmp_path: Path, cap: int) -> None:
    """Zero and anything above 1 SOL both report the range reason."""
    gate = _by_id(LiveGate(mode="live", environ={}, root=tmp_path, notional_cap_lamports=cap))
    assert gate["notional_cap"].met is False
    assert gate["notional_cap"].reason == CAP_RANGE


@pytest.mark.parametrize(
    ("allowlist", "cap"),
    [
        ((), None),
        ((SYSTEM_PROGRAM,), None),
        ((), LAMPORTS_PER_SOL),
        ((SYSTEM_PROGRAM,), LAMPORTS_PER_SOL),
        ((SYSTEM_PROGRAM,), 0),
    ],
)
def test_rows_8_and_9_stay_unmet(
    tmp_path: Path, allowlist: tuple[str, ...], cap: int | None
) -> None:
    """Adapter and halt-state rows remain unmet whatever rows 5 and 6 report."""
    gate = _by_id(
        LiveGate(
            mode="live",
            environ={"PUMPGROK_LIVE_ENABLE": "1"},
            root=tmp_path,
            live_enabled=True,
            wallet_allowlist=allowlist,
            notional_cap_lamports=cap,
        )
    )
    assert gate["adapter_registered"].met is False
    assert gate["adapter_registered"].reason == ADAPTER_UNMET
    assert gate["no_active_stop"].met is False
    assert gate["no_active_stop"].reason == HALT_UNMET
