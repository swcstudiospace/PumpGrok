"""Tracer: exec.place input contract rejects without approval (TOOL-004, B7).

Phase 3 scope only: missing/bad approval_id fails closed, exit+BUY is
refused with seat_may_trade before touching the adapter, and a valid shape
reaches the adapter and surfaces not_yet_implemented (never a fake Fill).
The atomic consume-and-order transaction is Phase 4 work.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import pytest
from pydantic import ValidationError

from pumpgrok.core.errors import NotYetImplemented
from pumpgrok.core.idempotency import exec_place_key
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.execution.not_yet_implemented import NotYetImplementedAdapter
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools.exec.place import PLACE_SPEC, PlaceIn, build_place_tool

MINT = "So11111111111111111111111111111111111111112"
TICKET = "SOL-20260201-001"
DECISION = "01" + "A" * 24
DECISION_2 = "01" + "B" * 24
APPROVAL = "apr-" + "C" * 26

SNIPER_BUDGET = RiskBudget()  # defaults may open exposure
EXIT_BUDGET = RiskBudget(
    max_trade_fraction=Decimal("0"),
    max_token_fraction=Decimal("0"),
    max_open_positions=0,
)


class _CountingAdapter(NotYetImplementedAdapter):
    """Refusing adapter that records whether place was reached."""

    def __init__(self) -> None:
        self.place_calls = 0

    async def place(self, request):  # type: ignore[override]
        self.place_calls += 1
        return await super().place(request)


def _buy(**overrides) -> dict:
    base = {
        "ticket_id": TICKET,
        "mint": MINT,
        "side": "buy",
        "decision_id": DECISION,
        "size_lamports": 100_000_000,
        "max_slippage_bps": 100,
        "approval_id": APPROVAL,
    }
    base.update(overrides)
    return base


def test_spec_is_paper_write_g6_no_retry() -> None:
    assert PLACE_SPEC.side_effect is SideEffect.PAPER_WRITE
    assert PLACE_SPEC.requires_approval is True
    assert PLACE_SPEC.timeout_s == 20.0
    assert PLACE_SPEC.retry.attempts == 1
    assert PLACE_SPEC.rate_limit_key == "exec"
    assert PLACE_SPEC.idempotent is True


def test_missing_approval_id_rejected_fail_closed() -> None:
    payload = _buy()
    del payload["approval_id"]
    with pytest.raises(ValidationError):
        PlaceIn.model_validate(payload)


def test_bad_approval_id_rejected_fail_closed() -> None:
    with pytest.raises(ValidationError):
        PlaceIn.model_validate(_buy(approval_id="human-said-yes"))
    with pytest.raises(ValidationError):
        PlaceIn.model_validate(_buy(approval_id="apr-short"))


async def test_exit_buy_refused_with_seat_may_trade_before_adapter() -> None:
    adapter = _CountingAdapter()
    tool = build_place_tool(adapter, lambda: EXIT_BUDGET, FixtureClock(start=1469918176.385))
    out = await tool(PlaceIn.model_validate(_buy()))
    assert out.status == "rejected"
    assert out.reason == "seat_may_trade"
    assert adapter.place_calls == 0


async def test_valid_shape_reaches_adapter_and_surfaces_not_yet_implemented() -> None:
    adapter = _CountingAdapter()
    tool = build_place_tool(adapter, lambda: SNIPER_BUDGET, FixtureClock(start=1469918176.385))
    with pytest.raises(NotYetImplemented) as excinfo:
        await tool(PlaceIn.model_validate(_buy()))
    assert excinfo.value.code == "not_yet_implemented"
    assert adapter.place_calls == 1


async def test_idempotency_key_covers_ticket_side_decision_only() -> None:
    adapter = _CountingAdapter()
    tool = build_place_tool(adapter, lambda: EXIT_BUDGET, FixtureClock(start=1469918176.385))
    out = await tool(PlaceIn.model_validate(_buy()))
    assert out.idempotency_key == exec_place_key(TICKET, "buy", DECISION)
    # A new decision is a new order (R23); tool/bot never enter the key.
    other = exec_place_key(TICKET, "buy", DECISION_2)
    assert other != out.idempotency_key
    assert out.idempotency_key == exec_place_key(TICKET, "buy", DECISION)


async def test_adapter_never_fakes_a_fill() -> None:
    adapter = NotYetImplementedAdapter()
    for method, kwargs in [
        ("quote", {"input_mint": MINT, "output_mint": MINT, "amount": 1, "slippage_bps": 100}),
        ("positions", {}),
    ]:
        with pytest.raises(NotYetImplemented) as excinfo:
            await getattr(adapter, method)(**kwargs)
        assert excinfo.value.code == "not_yet_implemented"


def test_size_must_match_side() -> None:
    with pytest.raises(ValidationError):
        PlaceIn.model_validate(_buy(size_lamports=None))
    with pytest.raises(ValidationError):
        PlaceIn.model_validate(_buy(side="sell", size_lamports=None))


def test_sell_with_token_units_is_accepted_shape() -> None:
    sell = _buy(side="sell", decision_id=DECISION_2)
    del sell["size_lamports"]
    sell["token_units"] = 500_000
    assert PlaceIn.model_validate(sell).token_units == 500_000
