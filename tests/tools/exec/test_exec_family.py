"""RED: exec family (quote/simulate/cancel/positions) over the refusing adapter.

- exec.quote delegates to ExecutionAdapter (raises not_yet_implemented)
- exec.simulate writes zero ledger events on any path
- exec.cancel requires order_id+ticket_id+approval_id, key over order_id
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import pytest
from pydantic import ValidationError

from pumpgrok.core.errors import NotYetImplemented
from pumpgrok.core.idempotency import exec_cancel_key
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.execution.not_yet_implemented import NotYetImplementedAdapter
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools.exec.cancel import CANCEL_SPEC, CancelIn, build_cancel_tool
from pumpgrok.tools.exec.positions import POSITIONS_SPEC, PositionsIn, build_positions_tool
from pumpgrok.tools.exec.quote import QUOTE_SPEC, QuoteIn, build_quote_tool
from pumpgrok.tools.exec.simulate import (
    SIMULATE_SPEC,
    SimulateIn,
    build_simulate_tool,
)

MINT = "So11111111111111111111111111111111111111112"
TICKET = "SOL-20260201-001"
ORDER = "01" + "D" * 24
APPROVAL = "apr-" + "C" * 26


def test_quote_spec_and_delegation() -> None:
    assert QUOTE_SPEC.side_effect is SideEffect.READ
    assert QUOTE_SPEC.timeout_s == 12.0
    assert QUOTE_SPEC.retry.attempts == 3
    assert QUOTE_SPEC.rate_limit_key == "jupiter"
    assert QUOTE_SPEC.requires_approval is False


async def test_quote_delegates_and_raises_not_yet_implemented() -> None:
    tool = build_quote_tool(NotYetImplementedAdapter(), FixtureClock(start=1469918176.385))
    with pytest.raises(NotYetImplemented) as excinfo:
        await tool(QuoteIn(input_mint=MINT, output_mint=MINT, amount=1_000_000))
    assert excinfo.value.code == "not_yet_implemented"


def test_simulate_spec_and_no_ledger_write(tmp_path: Path) -> None:
    assert SIMULATE_SPEC.side_effect is SideEffect.READ
    assert SIMULATE_SPEC.timeout_s == 10.0
    assert SIMULATE_SPEC.retry.attempts == 1
    assert SIMULATE_SPEC.rate_limit_key == "solana_rpc"
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    assert store.count() == 0
    store.close()


async def test_simulate_writes_zero_ledger_events(tmp_path: Path) -> None:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    tool = build_simulate_tool()
    with pytest.raises(NotYetImplemented) as excinfo:
        await tool(SimulateIn(ticket_id=TICKET, mint=MINT, side="buy", size_lamports=100_000_000))
    assert excinfo.value.code == "not_yet_implemented"
    assert store.count() == 0
    store.close()


def test_cancel_spec_and_key() -> None:
    assert CANCEL_SPEC.side_effect is SideEffect.PAPER_WRITE
    assert CANCEL_SPEC.timeout_s == 10.0
    assert CANCEL_SPEC.retry.attempts == 1
    assert CANCEL_SPEC.rate_limit_key == "exec"
    assert CANCEL_SPEC.requires_approval is True
    assert CANCEL_SPEC.idempotent is True


async def test_cancel_requires_approval_and_derives_key() -> None:
    tool = build_cancel_tool()
    with pytest.raises(ValidationError):
        CancelIn.model_validate({"order_id": ORDER, "ticket_id": TICKET})
    with pytest.raises(NotYetImplemented) as excinfo:
        await tool(CancelIn(order_id=ORDER, ticket_id=TICKET, approval_id=APPROVAL))
    assert excinfo.value.code == "not_yet_implemented"
    assert exec_cancel_key(ORDER) == exec_cancel_key(ORDER)
    assert len(exec_cancel_key(ORDER)) == 32


def test_positions_spec() -> None:
    assert POSITIONS_SPEC.side_effect is SideEffect.READ
    assert POSITIONS_SPEC.timeout_s == 10.0
    assert POSITIONS_SPEC.retry.attempts == 1
    assert POSITIONS_SPEC.rate_limit_key == "ledger"


async def test_positions_delegates_and_raises() -> None:
    tool = build_positions_tool(NotYetImplementedAdapter(), FixtureClock(start=1469918176.385))
    with pytest.raises(NotYetImplemented) as excinfo:
        await tool(PositionsIn())
    assert excinfo.value.code == "not_yet_implemented"
