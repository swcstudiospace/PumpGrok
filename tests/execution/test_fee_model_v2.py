"""FEE-01: fee model v2 (ATA rent on first buy, PumpPortal term, priority cap).

Integer lamports throughout. ATA rent is read at runtime from RPC; the pinned value
is the offline replay fallback and records its epoch and source. The stale 2039280
is never used.
"""

from __future__ import annotations

import asyncio
import random
from types import SimpleNamespace
from typing import Any

import pytest

from pumpgrok.core.adapter import Fill, OrderRequest, Side
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution import build_paper_adapter
from pumpgrok.execution.deposits import open_deposits
from pumpgrok.execution.fees import (
    ATA_RENT_OFFLINE_EPOCH,
    ATA_RENT_OFFLINE_LAMPORTS,
    BASE_FEE_LAMPORTS,
    COMPUTE_UNITS,
    PAPER_DEFAULT_FEE_MODEL,
    FeeModel,
    FeeModelV2,
    read_ata_rent,
)
from pumpgrok.execution.paper_adapter import PaperAdapter
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine

from .replay_support import replay_authority, tick

START = 1_769_900_000.0
EQUITY = 10_000_000_000
MINT = "So11111111111111111111111111111111111111112"
TICKET_A = "SOL-20260201-001"
TICKET_B = "SOL-20260201-002"
S0 = 42_000_000_000
T0 = 766_428_571_428_571
SIZE = 200_000_000
STALE_RENT = 2_039_280


class _RentRpc:
    """Read-only RPC double: records each call and returns a fixed result."""

    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[tuple[str, list[Any]]] = []

    async def call(self, method: str, params: list[Any]) -> Any:
        self.calls.append((method, params))
        return self.result


def test_v2_extends_v1_and_v1_is_unchanged() -> None:
    assert issubclass(FeeModelV2, FeeModel)
    v1 = FeeModel()
    assert v1.priority_fee() == 20_000 * COMPUTE_UNITS // 1_000_000
    assert v1.network_cost() == BASE_FEE_LAMPORTS + v1.priority_fee()
    assert v1.buy_debit(SIZE) == SIZE + v1.network_cost()


def test_paper_default_is_v2_with_offline_pin_epoch_and_source() -> None:
    assert isinstance(PAPER_DEFAULT_FEE_MODEL, FeeModelV2)
    assert ATA_RENT_OFFLINE_LAMPORTS == 1_488_440
    assert PAPER_DEFAULT_FEE_MODEL.ata_rent_lamports == ATA_RENT_OFFLINE_LAMPORTS
    assert ATA_RENT_OFFLINE_EPOCH == 1033
    assert PAPER_DEFAULT_FEE_MODEL.ata_rent_epoch == ATA_RENT_OFFLINE_EPOCH
    assert PAPER_DEFAULT_FEE_MODEL.ata_rent_source.startswith("offline-pinned")


def test_stale_rent_is_not_used_anywhere_in_the_default() -> None:
    assert PAPER_DEFAULT_FEE_MODEL.ata_rent_lamports != STALE_RENT
    assert FeeModelV2().ata_rent_lamports != STALE_RENT


def test_ata_rent_is_charged_on_first_buy_only() -> None:
    fees = FeeModelV2()
    first = fees.buy_debit_v2(SIZE, first_buy=True)
    repeat = fees.buy_debit_v2(SIZE, first_buy=False)
    assert first == SIZE + fees.network_cost() + ATA_RENT_OFFLINE_LAMPORTS
    assert repeat == SIZE + fees.network_cost()
    assert type(first) is int and type(repeat) is int


def test_pumpportal_term_is_zero_unless_the_builder_is_selected() -> None:
    assert FeeModelV2().pumpportal_fee_bps == 0
    base = FeeModelV2().buy_debit_v2(SIZE, first_buy=False)
    assert FeeModelV2().buy_debit_v2(SIZE, first_buy=False, pumpportal_builder=True) == base
    priced = FeeModelV2(pumpportal_fee_bps=100)
    assert priced.buy_debit_v2(SIZE, first_buy=False, pumpportal_builder=False) == base
    assert priced.buy_debit_v2(SIZE, first_buy=False, pumpportal_builder=True) == (
        base + SIZE * 100 // 10_000
    )


def test_priority_cost_is_clamped_to_the_cap_before_the_formula() -> None:
    capped = FeeModelV2(micro_lamports_per_cu=50_000, priority_cap_micro_lamports_per_cu=20_000)
    assert capped.priority_fee() == 20_000 * COMPUTE_UNITS // 1_000_000
    assert FeeModelV2().priority_fee() == FeeModel().priority_fee()


def test_runtime_rent_read_replaces_the_offline_pin_and_records_its_source() -> None:
    rpc = _RentRpc(1_500_000)
    fees = asyncio.run(read_ata_rent(rpc))
    assert rpc.calls == [("getMinimumBalanceForRentExemption", [165])]
    assert fees.ata_rent_lamports == 1_500_000
    assert fees.ata_rent_epoch is None
    assert fees.ata_rent_source == "rpc:getMinimumBalanceForRentExemption(165)"
    assert fees.priority_fee() == PAPER_DEFAULT_FEE_MODEL.priority_fee()


@pytest.mark.parametrize("bad", [None, "1488440", 0, -1, True, 1.5])
def test_runtime_rent_read_refuses_a_non_integer_or_non_positive_result(bad: Any) -> None:
    with pytest.raises(ValueError):
        asyncio.run(read_ata_rent(_RentRpc(bad)))


def _store(path: Any) -> LedgerStore:
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "replay")
    return store


def _adapter(
    store: LedgerStore, clock: FixtureClock, replay: Any, *, fees: FeeModel | None = None
) -> PaperAdapter:
    seed = 7
    engine = RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(seed)),
        clock=clock,
        autonomy="autonomous-paper",  # type: ignore[arg-type]
        get_reserves=lambda _mint: (S0, T0),
    )
    return build_paper_adapter(
        SimpleNamespace(),
        store=store,
        risk=engine,
        ids=IdFactory(clock, make_rng(seed)),
        clock=clock,
        rng=make_rng(seed),
        replay=replay,
        source="replay",
        p_drop=0.0,
        fees=fees,
    )


def _order(ticket: str, side: Side, decision_id: str, *, units: int | None = None) -> OrderRequest:
    buy = side is Side.BUY
    return OrderRequest(
        ticket_id=ticket,
        mint=MINT,
        side=side,
        decision_id=decision_id,
        size_lamports=SIZE if buy else None,
        token_units=None if buy else units,
        max_slippage_bps=100,
        approval_id=f"apr-{decision_id}",
        correlation_id="test",
    )


async def _place(
    adapter: PaperAdapter,
    clock: FixtureClock,
    request: OrderRequest,
    *,
    seat: str = "bot-04-sniper",
) -> Fill:
    task = asyncio.create_task(adapter.place(request, seat=seat, correlation_id="test"))
    for _ in range(400):
        if task.done():
            break
        clock.advance_to(clock.now() + 1.0)
        await asyncio.sleep(0)
    return await task


def _buy_fill_payloads(store: LedgerStore) -> list[dict[str, Any]]:
    rows = store.read(types=["FillRecorded"], limit=None)
    return [row["payload"] for row in rows if row["payload"]["side"] == "buy"]


def test_rent_follows_the_first_buy_of_a_mint_across_a_restart(tmp_path: Any) -> None:
    clock = FixtureClock(START)
    store = _store(tmp_path / "ledger.sqlite")
    ticks = [tick(START + 60.0 * i, MINT, S0, T0) for i in range(60)]
    replay = replay_authority(tmp_path, clock, ticks)
    ids = IdFactory(clock, make_rng(9))
    base = FeeModel().network_cost()

    async def scenario() -> tuple[Fill, Fill, Fill]:
        adapter = _adapter(store, clock, replay)
        first = await _place(adapter, clock, _order(TICKET_A, Side.BUY, ids.ulid()))
        assert await adapter.mark_to_market(MINT, correlation_id="test") is not None
        sold = await _place(
            adapter,
            clock,
            _order(TICKET_A, Side.SELL, ids.ulid(), units=first.filled_units),
            seat="bot-06-exit",
        )
        # A restart composes a new adapter over the same ledger; the first-buy decision
        # reads the recorded fills, so the repeat buy of the same mint pays no rent.
        second = await _place(
            _adapter(store, clock, replay), clock, _order(TICKET_B, Side.BUY, ids.ulid())
        )
        return first, sold, second

    first, sold, second = asyncio.run(scenario())
    assert sold.filled_units == first.filled_units
    assert first.network_cost_lamports == base + ATA_RENT_OFFLINE_LAMPORTS
    assert second.network_cost_lamports == base
    fills = _buy_fill_payloads(store)
    assert [f["network_cost_lamports"] for f in fills] == [
        base + ATA_RENT_OFFLINE_LAMPORTS,
        base,
    ]
    assert fills[0]["cash_delta_lamports"] == -(
        fills[0]["filled_lamports"] + base + ATA_RENT_OFFLINE_LAMPORTS
    )
    store.close()


def test_explicit_v1_selection_charges_no_rent(tmp_path: Any) -> None:
    clock = FixtureClock(START)
    store = _store(tmp_path / "ledger.sqlite")
    replay = replay_authority(tmp_path, clock, [tick(START, MINT, S0, T0)])
    ids = IdFactory(clock, make_rng(9))
    fill = asyncio.run(
        _place(
            _adapter(store, clock, replay, fees=FeeModel()),
            clock,
            _order(TICKET_A, Side.BUY, ids.ulid()),
        )
    )
    assert fill.network_cost_lamports == FeeModel().network_cost()
    store.close()


def test_deposit_term_is_the_rent_on_a_v2_first_buy_and_zero_otherwise() -> None:
    assert FeeModel().ata_deposit_term(first_buy=True) == 0
    assert FeeModelV2().ata_deposit_term(first_buy=True) == ATA_RENT_OFFLINE_LAMPORTS
    assert FeeModelV2().ata_deposit_term(first_buy=False) == 0


def _sell_fill_payloads(store: LedgerStore) -> list[dict[str, Any]]:
    rows = store.read(types=["FillRecorded"], limit=None)
    return [row["payload"] for row in rows if row["payload"]["side"] == "sell"]


def _run_lifecycle(
    root: Any, fees: FeeModel, *, forced: bool, partial: bool = False
) -> dict[str, Any]:
    """Buy, mark, then close: a full sell, a partial sell, or a forced close."""
    root.mkdir(parents=True)
    clock = FixtureClock(START)
    store = _store(root / "ledger.sqlite")
    ticks = [tick(START + 60.0 * i, MINT, S0, T0) for i in range(60)]
    replay = replay_authority(root, clock, ticks)
    ids = IdFactory(clock, make_rng(9))

    async def no_curve(_mint: str) -> None:
        return None

    async def scenario() -> dict[str, Any]:
        adapter = _adapter(store, clock, replay, fees=fees)
        steps: dict[str, Any] = {"start": adapter.equity_lamports()}
        first = await _place(adapter, clock, _order(TICKET_A, Side.BUY, ids.ulid()))
        steps["after_buy"] = adapter.equity_lamports()
        steps["deposit_after_buy"] = open_deposits(store)
        assert await adapter.mark_to_market(MINT, correlation_id="test") is not None
        steps["at_mark"] = adapter.equity_lamports()
        if forced:
            adapter._read_curve = no_curve  # type: ignore[method-assign]
            closed = await adapter.close_position(
                mint=MINT, ticket_id=TICKET_A, reason="kill_flatten"
            )
            steps["proceeds"] = closed["proceeds_lamports"]
            steps["realized"] = closed["realized_pnl_lamports"]
            again = await adapter.close_position(
                mint=MINT, ticket_id=TICKET_A, reason="kill_flatten"
            )
            steps["second_close"] = again["status"]
        else:
            units = first.filled_units // 2 if partial else first.filled_units
            await _place(
                adapter,
                clock,
                _order(TICKET_A, Side.SELL, ids.ulid(), units=units),
                seat="bot-06-exit",
            )
        steps["after_close"] = adapter.equity_lamports()
        steps["buy"] = _buy_fill_payloads(store)[0]
        steps["sells"] = _sell_fill_payloads(store)
        closes = store.read(types=["PositionClosed"], limit=None)
        steps["closes"] = [row["payload"] for row in closes]
        return steps

    try:
        return asyncio.run(scenario())
    finally:
        store.close()


def test_rent_is_a_deposit_asset_until_the_account_closes(tmp_path: Any) -> None:
    v2 = _run_lifecycle(tmp_path / "v2", PAPER_DEFAULT_FEE_MODEL, forced=False)
    v1 = _run_lifecycle(tmp_path / "v1", FeeModel(), forced=False)
    assert v2["after_buy"] == v2["start"], "the buy itself moves no equity"
    assert v2["at_mark"] == v1["at_mark"], "the first mark carries the rent as an asset"
    assert v2["deposit_after_buy"] == {MINT: ATA_RENT_OFFLINE_LAMPORTS}
    assert v1["deposit_after_buy"] == {MINT: 0}
    assert v2["after_close"] == v1["after_close"], "the full close refunds the rent to cash"


def test_a_full_close_credits_the_deposit_to_cash_once_and_keeps_it_out_of_realized(
    tmp_path: Any,
) -> None:
    v2 = _run_lifecycle(tmp_path / "v2", PAPER_DEFAULT_FEE_MODEL, forced=False)
    v1 = _run_lifecycle(tmp_path / "v1", FeeModel(), forced=False)
    [sell] = v2["sells"]
    [closed] = v2["closes"]
    [v1_closed] = v1["closes"]
    rent = ATA_RENT_OFFLINE_LAMPORTS
    cost_basis_ex_rent = v2["buy"]["filled_lamports"] + v2["buy"]["network_cost_lamports"] - rent
    assert sell["cash_delta_lamports"] == sell["filled_lamports"] + rent, "refund in the close"
    assert closed["realized_pnl_lamports"] == sell["filled_lamports"] - cost_basis_ex_rent
    assert closed["realized_pnl_lamports"] == v1_closed["realized_pnl_lamports"]


def test_a_partial_sell_keeps_the_deposit_whole_until_the_full_close(tmp_path: Any) -> None:
    v2 = _run_lifecycle(tmp_path / "v2", PAPER_DEFAULT_FEE_MODEL, forced=False, partial=True)
    [sell] = v2["sells"]
    assert sell["cash_delta_lamports"] == sell["filled_lamports"], "no rent leaves on a partial"
    assert v2["closes"] == [], "a partial exit closes nothing"


def test_a_forced_close_returns_the_deposit_once_inside_market_value(
    tmp_path: Any,
) -> None:
    v2 = _run_lifecycle(tmp_path / "v2", PAPER_DEFAULT_FEE_MODEL, forced=True)
    v1 = _run_lifecycle(tmp_path / "v1", FeeModel(), forced=True)
    [sell] = v2["sells"]
    # Market value 195677515 (sale value plus the held deposit) less the 9000 network cost.
    assert v2["proceeds"] == 195668515, "proceeds are market value less network cost"
    assert sell["cash_delta_lamports"] == v2["proceeds"], "the deposit is inside market value"
    assert v2["realized"] == v1["realized"], "realized excludes the rent"
    assert v2["after_close"] == v1["after_close"], "the rent comes back to cash once"
    assert v2["second_close"] == "no_position", "a closed position refunds nothing again"
