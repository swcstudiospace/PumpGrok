"""RT-03 / RSK-05: the composition root passes the holder-pair flag into the entry check.

While no paid RPC provider is recorded, a BLIND SAFE-4 holder row only warns. Once one is
recorded it rejects. The flag reads .planning/STATE.md under the working directory, so each case
runs in its own temporary directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from datafeed.readonly_double import ReadOnlyDouble
from pumpgrok.config.settings import Settings
from pumpgrok.events.event_desk import EventDesk, build_event_desk
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.risk.entry_checks import EntryEvidence
from pumpgrok.tools.safety.checks import CheckResult

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


def _blind_holder_evidence() -> EntryEvidence:
    """Every required row passes except the SAFE-4 top-10 holder row, which is BLIND."""
    checks = [
        CheckResult(
            id=check_id,  # type: ignore[arg-type]
            status="blind" if check_id == "top10_concentration" else "pass",
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


def _entry_evidence(mint: str) -> EntryEvidence | None:
    return _blind_holder_evidence() if mint == MINT else None


async def _unused_grok(_request: Any, _text: str) -> str:
    raise AssertionError("the holder-flag test makes no Grok call")


async def _build(tmp_path: Path) -> EventDesk:
    return await build_event_desk(
        Settings(mode="paper"),
        data_dir=tmp_path / "desk",
        clock=FixtureClock(START),
        rpc_transport=ReadOnlyDouble(),
        grok_transport=_unused_grok,
        strategies=(),
        evidence=lambda _strategy_id: None,
        entry_evidence=_entry_evidence,
    )


@pytest.mark.parametrize(
    ("record", "advisory"),
    [
        (None, False),
        ("paid_rpc_provider: none\n", True),
        ("paid_rpc_provider: helius\n", False),
    ],
    ids=["no-record-file", "record-none", "record-paid-provider"],
)
async def test_holder_flag_reaches_the_entry_check_through_the_composition_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record: str | None,
    advisory: bool,
) -> None:
    monkeypatch.chdir(tmp_path)
    if record is not None:
        (tmp_path / ".planning").mkdir()
        (tmp_path / ".planning" / "STATE.md").write_text(record, encoding="utf-8")
    desk = await _build(tmp_path)
    try:
        await desk.start()
        gate = desk.entry_gate
        assert gate.holder_blind_advisory is advisory

        detail = gate.check.refusal(
            MINT,
            None,
            cast(Any, None),
            holder_blind_advisory=gate.holder_blind_advisory,
        )
        # Advisory: the BLIND holder row warns and the mint is admitted. Otherwise it rejects.
        assert (detail is None) is advisory
    finally:
        await desk.close()
