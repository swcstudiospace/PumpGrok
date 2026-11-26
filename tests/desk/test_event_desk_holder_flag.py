"""RT-03 / RSK-05: the composition root passes the holder-pair flag into the entry check.

While no paid RPC provider is recorded, a BLIND SAFE-4 holder row only warns. Once one is
recorded it rejects. The flag reads .planning/STATE.md under the working directory, so each case
runs in its own temporary directory.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.config.settings import SafetyThresholds
from pumpgrok.core.adapter import ExecutionMode
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.risk.entry_checks import (
    EntryChecks,
    EntryEvidence,
    MintLists,
    evaluate_entry,
)
from pumpgrok.supervisor.event_desk import build_event_desk
from pumpgrok.tools.safety.checks import CheckId, CheckResult

START = 1_700_000_000.0
MINT = "MintDeskHolder"
_REQUIRED_IDS = (
    "mint_authority",
    "freeze_authority",
    "lp_status",
    "top10_concentration",
    "deployer_history",
    "token2022_extensions",
    "liquidity_depth",
)
EMPTY_LISTS = MintLists(deny=frozenset(), warn=frozenset())


def _blind_holder_evidence() -> EntryEvidence:
    """Every required row passes except the SAFE-4 top-10 holder row, which is BLIND."""
    checks = [
        CheckResult(
            id=cast(CheckId, check_id),
            status=cast(Any, "blind" if check_id == "top10_concentration" else "pass"),
            weight=Decimal("0.1"),
            reason=f"{check_id} test row",
        )
        for check_id in _REQUIRED_IDS
    ]
    return EntryEvidence(
        mint=MINT,
        authorities={"has_mint_authority": False, "has_freeze_authority": False},
        extensions=(),
        top10_share=0.1,
        checks=checks,
    )


def _store(tmp_path: Path) -> LedgerStore:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", "10000000000")
    store.set_meta("source", "paper")
    return store


@pytest.mark.parametrize(
    ("record", "advisory"),
    [
        (None, False),
        ("paid_rpc_provider: none\n", True),
        ("paid_rpc_provider: helius\n", False),
    ],
    ids=["no-record-file", "record-none", "record-paid-provider"],
)
def test_holder_flag_reaches_the_entry_check_through_the_composition_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record: str | None,
    advisory: bool,
) -> None:
    monkeypatch.chdir(tmp_path)
    if record is not None:
        (tmp_path / ".planning").mkdir()
        (tmp_path / ".planning" / "STATE.md").write_text(record, encoding="utf-8")
    desk = build_event_desk(
        mode=ExecutionMode.PAPER,
        store=_store(tmp_path),
        clock=FixtureClock(start=START),
        place=lambda intent: None,
        entry_checks=EntryChecks(),
        sidecar_path=tmp_path / "sidecar.sqlite",
        params={"momentum_breakout": {"breakout_bps": 100}},
    )
    assert desk.holder_blind_advisory is advisory
    assert desk.entry_checks is not None
    assert desk.entry_checks.holder_blind_advisory is advisory

    verdict = evaluate_entry(
        _blind_holder_evidence(),
        EMPTY_LISTS,
        SafetyThresholds(),
        holder_blind_advisory=desk.holder_blind_advisory,
    )
    # Advisory: the BLIND holder row warns and the mint is admitted. Otherwise it rejects.
    assert verdict.ok is advisory
