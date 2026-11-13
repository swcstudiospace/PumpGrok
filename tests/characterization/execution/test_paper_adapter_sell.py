"""Characterization pins for PaperAdapter sell placement (``_place_sell``).

Each scenario runs the unsplit adapter on a fresh ledger and records the
returned outcome (fill fields or refusal) together with every ledger row,
hash included. The digests in ``PINS`` were recorded on the unsplit code
(CONTEXT D-10) and must still hold after ``sell_stages.py`` lands.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
from collections.abc import Awaitable, Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from replay_timeline import Tick, build_replay_adapter

from pumpgrok.core.adapter import Fill, OrderRequest, Side
from pumpgrok.core.errors import OrderRejectedError
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import SELL_SEAT, RiskEngine

START = 1_769_900_000.0
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-001"
SELL_TICKET = "SOL-20260201-002"
MINT = "So11111111111111111111111111111111111111112"
S0 = 42_000_000_000
T0 = 766_428_571_428_571
SIZE = 200_000_000


#: The curve is one open tick at START: every read prices at (S0, T0).
CURVE: tuple[Tick, ...] = ((0.0, S0, T0, False),)
#: Sell slippage: S falls 5% between the sell's ACCEPTED read (+4.0s) and its CONFIRMING
#: read (+5.0s, one drive step later). The BUY reads (+1s, +3s) stay at (S0, T0).
SLIPPAGE_AT_S = 4.5
SLIPPAGE: tuple[Tick, ...] = (
    (0.0, S0, T0, False),
    (SLIPPAGE_AT_S, S0 - S0 // 20, T0, False),
)


class Harness:
    def __init__(
        self,
        root: Path,
        timeline: tuple[Tick, ...] = CURVE,
        *,
        autonomy: str = "autonomous-paper",
        seed: int = 7,
    ) -> None:
        self.clock = FixtureClock(START)
        self.store = LedgerStore(str(root / "ledger.sqlite"))
        self.store.set_meta("initial_equity_lamports", str(EQUITY))
        self.store.set_meta("source", "replay")
        self.ids = IdFactory(self.clock, make_rng(seed))
        budget = RiskBudget()
        self.risk = RiskEngine(
            store=self.store,
            budget=budget,
            ids=IdFactory(self.clock, random.Random(seed)),
            clock=self.clock,
            autonomy=autonomy,
            get_reserves=lambda _mint: (S0, T0),
        )
        self.adapter = build_replay_adapter(
            root,
            self.clock,
            self.store,
            self.risk,
            self.ids,
            make_rng(seed),
            budget,
            mint=MINT,
            start=START,
            timeline=timeline,
        )

    async def drive(self, *coros: Awaitable[Any]) -> list[Any]:
        """Advance virtual time until every call settles; errors come back as values."""
        tasks = [asyncio.create_task(c) for c in coros]
        for _ in range(400):
            if all(t.done() for t in tasks):
                break
            self.clock.advance_to(self.clock.now() + 1.0)
            await asyncio.sleep(0)
        results: list[Any] = []
        for task in tasks:
            if not task.done():
                task.cancel()
                raise AssertionError("scenario did not settle in virtual time")
            try:
                results.append(await task)
            except Exception as exc:
                results.append(exc)
        return results

    def buy_request(self) -> OrderRequest:
        return OrderRequest(
            ticket_id=TICKET,
            mint=MINT,
            side=Side.BUY,
            decision_id=self.ids.ulid(),
            size_lamports=SIZE,
            max_slippage_bps=100,
            approval_id=f"apr-{self.ids.ulid()}",
            correlation_id="test",
        )

    def sell_request(
        self,
        *,
        units: int | None = None,
        size: int | None = None,
        exit_reason: str | None = None,
    ) -> OrderRequest:
        return OrderRequest(
            ticket_id=SELL_TICKET,
            mint=MINT,
            side=Side.SELL,
            decision_id=self.ids.ulid(),
            token_units=units,
            size_lamports=size,
            max_slippage_bps=100,
            approval_id=f"apr-{self.ids.ulid()}",
            exit_reason=exit_reason,
            correlation_id="test",
        )

    async def open_position(self) -> Fill:
        result = await self.drive(
            self.adapter.place(self.buy_request(), seat="bot-04-sniper", correlation_id="test")
        )
        fill = result[0]
        assert isinstance(fill, Fill)
        await self.adapter.mark_to_market(MINT, correlation_id="test")
        return fill

    def ledger(self) -> list[dict[str, Any]]:
        return [dict(event) for event in self.store.read(limit=None)]


def outcome(value: Any) -> dict[str, Any]:
    if isinstance(value, Fill):
        return {"fill": value.model_dump(mode="json")}
    if isinstance(value, OrderRejectedError):
        return {
            "error": type(value).__name__,
            "reason": value.reason,
            "stage": value.stage,
            "fees": value.fees_lamports,
            "message": str(value),
        }
    raise AssertionError(f"unexpected outcome {value!r}")


def digest(trace: dict[str, Any]) -> str:
    text = json.dumps(trace, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


async def scn_sell_full_close(root: Path) -> dict[str, Any]:
    h = Harness(root)
    buy = await h.open_position()
    sell = await h.drive(
        h.adapter.place(
            h.sell_request(units=buy.filled_units), seat=SELL_SEAT, correlation_id="test"
        )
    )
    return {"outcome": outcome(sell[0]), "rows": h.ledger()}


async def scn_sell_partial_over_holding(root: Path) -> dict[str, Any]:
    h = Harness(root)
    buy = await h.open_position()
    sell = await h.drive(
        h.adapter.place(
            h.sell_request(units=buy.filled_units * 2), seat=SELL_SEAT, correlation_id="test"
        )
    )
    return {"outcome": outcome(sell[0]), "rows": h.ledger()}


async def scn_sell_size_based(root: Path) -> dict[str, Any]:
    h = Harness(root)
    await h.open_position()
    sell = await h.drive(
        h.adapter.place(h.sell_request(size=SIZE // 2), seat=SELL_SEAT, correlation_id="test")
    )
    return {"outcome": outcome(sell[0]), "rows": h.ledger()}


async def scn_sell_no_position(root: Path) -> dict[str, Any]:
    h = Harness(root)
    sell = await h.drive(
        h.adapter.place(h.sell_request(units=1_000_000), seat=SELL_SEAT, correlation_id="test")
    )
    return {"outcome": outcome(sell[0]), "rows": h.ledger()}


async def scn_sell_below_liquidity_floor(root: Path) -> dict[str, Any]:
    h = Harness(root)
    await h.open_position()
    sell = await h.drive(
        h.adapter.place(h.sell_request(units=T0 // 5), seat=SELL_SEAT, correlation_id="test")
    )
    return {"outcome": outcome(sell[0]), "rows": h.ledger()}


async def scn_sell_no_reserves_accepted(root: Path) -> dict[str, Any]:
    # Verified replay cannot remove a curve once a tick exists: the ACCEPTED read stays priced.
    h = Harness(root)
    buy = await h.open_position()
    sell = await h.drive(
        h.adapter.place(
            h.sell_request(units=buy.filled_units), seat=SELL_SEAT, correlation_id="test"
        )
    )
    return {"outcome": outcome(sell[0]), "rows": h.ledger()}


async def scn_sell_slippage_confirming(root: Path) -> dict[str, Any]:
    h = Harness(root, SLIPPAGE)
    buy = await h.open_position()
    sell = await h.drive(
        h.adapter.place(
            h.sell_request(units=buy.filled_units), seat=SELL_SEAT, correlation_id="test"
        )
    )
    return {"outcome": outcome(sell[0]), "rows": h.ledger()}


async def scn_sell_no_reserves_confirming(root: Path) -> dict[str, Any]:
    # Verified replay cannot remove a curve once a tick exists: the CONFIRMING read stays priced.
    h = Harness(root)
    buy = await h.open_position()
    sell = await h.drive(
        h.adapter.place(
            h.sell_request(units=buy.filled_units), seat=SELL_SEAT, correlation_id="test"
        )
    )
    return {"outcome": outcome(sell[0]), "rows": h.ledger()}


async def scn_sell_concurrent_confirming(root: Path) -> dict[str, Any]:
    h = Harness(root)
    buy = await h.open_position()
    first = h.sell_request(units=buy.filled_units)
    second = h.sell_request(units=buy.filled_units)
    results = await h.drive(
        h.adapter.place(first, seat=SELL_SEAT, correlation_id="test"),
        h.adapter.place(second, seat=SELL_SEAT, correlation_id="test"),
    )
    return {"outcomes": [outcome(r) for r in results], "rows": h.ledger()}


async def scn_sell_repeat_replays_fill(root: Path) -> dict[str, Any]:
    h = Harness(root)
    buy = await h.open_position()
    request = h.sell_request(units=buy.filled_units)
    first = await h.drive(h.adapter.place(request, seat=SELL_SEAT, correlation_id="test"))
    second = await h.drive(h.adapter.place(request, seat=SELL_SEAT, correlation_id="test"))
    return {"first": outcome(first[0]), "second": outcome(second[0]), "rows": h.ledger()}


async def scn_sell_direct_place_sell(root: Path) -> dict[str, Any]:
    h = Harness(root)
    buy = await h.open_position()
    request = h.sell_request(units=buy.filled_units)
    curve0 = await h.adapter._read_curve(MINT)
    assert curve0 is not None
    result = await h.drive(
        h.adapter._place_sell(
            request,
            curve0=curve0,
            ledger_source="replay",
            correlation_id="test",
            seat=SELL_SEAT,
            exit_reason=None,
            creator=None,
            owner=object(),
        )
    )
    return {"outcome": outcome(result[0]), "rows": h.ledger()}


SCENARIOS: dict[str, Callable[[Path], Awaitable[dict[str, Any]]]] = {
    "sell_full_close": scn_sell_full_close,
    "sell_partial_over_holding": scn_sell_partial_over_holding,
    "sell_size_based": scn_sell_size_based,
    "sell_no_position": scn_sell_no_position,
    "sell_below_liquidity_floor": scn_sell_below_liquidity_floor,
    "sell_no_reserves_accepted": scn_sell_no_reserves_accepted,
    "sell_slippage_confirming": scn_sell_slippage_confirming,
    "sell_no_reserves_confirming": scn_sell_no_reserves_confirming,
    "sell_concurrent_confirming": scn_sell_concurrent_confirming,
    "sell_repeat_replays_fill": scn_sell_repeat_replays_fill,
    "sell_direct_place_sell": scn_sell_direct_place_sell,
}

_PIN_TABLE = """
sell_full_close 9609c4d67f584dd510ef1342bfa38abade458bd33412d39e3b124744ce8d970f
sell_partial_over_holding 467c93dd75e7f74f42e7f4352183426d729f4f0a903518683a371029cbc2be9e
sell_size_based 9d09b93e5af648b27857141291929f0b58fabfbc141654f0f5d3ae291207fde5
sell_no_position fdf23860ea45f42554e1ad6bd286c11b71869061ff4356dd1f9be6dfea61e6b4
sell_below_liquidity_floor ee9a0962e0105c4312f456708fad160b0112accf9809ac049340a634aaffe70a
sell_no_reserves_accepted d641bac555fc17490e3630e4e16d8875b5a369f7aeea4003673ea40acc02c088
sell_slippage_confirming bf960666c80165171521d10530f5619911dc6b11b5478aadbf4ac62067e1e821
sell_no_reserves_confirming 004e0dfa9e642f1507068447c265b7722e2b5a53ebf2f7cc582efc7db5ed8e52
sell_concurrent_confirming e97d9b82b2196fa1b343f7971157f21c928fa85e9e51e8e2705bb0b21a28243e
sell_repeat_replays_fill 35fa9379d431f60d3aacccf217920240d1c5c5195c199757b5eca551c51a6fee
sell_direct_place_sell 9609c4d67f584dd510ef1342bfa38abade458bd33412d39e3b124744ce8d970f
"""
PINS: dict[str, str] = dict(line.split() for line in _PIN_TABLE.strip().splitlines())


@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_sell_scenario_matches_pinned_digest(tmp_path: Path, name: str) -> None:
    trace = await SCENARIOS[name](tmp_path)
    assert digest(trace) == PINS[name]


async def test_full_close_fills_and_closes_the_position(tmp_path: Path) -> None:
    trace = await scn_sell_full_close(tmp_path)
    assert trace["outcome"]["fill"]["status"] == "filled"
    kinds = [row["type"] for row in trace["rows"]]
    assert kinds[-2:] == ["FillRecorded", "PositionClosed"]


async def test_over_holding_exit_is_partial_not_clipped_silently(tmp_path: Path) -> None:
    trace = await scn_sell_partial_over_holding(tmp_path)
    fill = trace["outcome"]["fill"]
    assert fill["status"] == "partial"
    assert fill["filled_units"] > 0
    assert Decimal(fill["filled_fraction"]) < 1


async def test_flat_sell_refuses_no_position_at_accepted(tmp_path: Path) -> None:
    trace = await scn_sell_no_position(tmp_path)
    assert trace["outcome"]["reason"] == "no_position"
    assert trace["outcome"]["stage"] == "ACCEPTED"


async def test_oversize_sell_refuses_below_liquidity_floor(tmp_path: Path) -> None:
    trace = await scn_sell_below_liquidity_floor(tmp_path)
    assert trace["outcome"]["reason"] == "below_liquidity_floor"
    assert trace["outcome"]["stage"] == "ACCEPTED"


async def test_slippage_refuses_at_confirming_and_charges_network_cost(tmp_path: Path) -> None:
    trace = await scn_sell_slippage_confirming(tmp_path)
    assert trace["outcome"]["reason"] == "slippage_exceeded"
    assert trace["outcome"]["stage"] == "CONFIRMING"
    assert trace["outcome"]["fees"] > 0
    kinds = [row["type"] for row in trace["rows"]]
    assert kinds.count("FillRecorded") == 1
    assert "PositionClosed" not in kinds


async def test_concurrent_exits_fill_once_and_refuse_the_other_at_confirming(
    tmp_path: Path,
) -> None:
    trace = await scn_sell_concurrent_confirming(tmp_path)
    fills = [o for o in trace["outcomes"] if "fill" in o]
    refusals = [o for o in trace["outcomes"] if "reason" in o]
    assert len(fills) == 1
    assert len(refusals) == 1
    assert refusals[0]["reason"] == "no_position"
    assert refusals[0]["stage"] == "CONFIRMING"


async def test_repeated_sell_replays_the_first_fill(tmp_path: Path) -> None:
    trace = await scn_sell_repeat_replays_fill(tmp_path)
    assert trace["second"] == trace["first"]
    fills = [row for row in trace["rows"] if row["type"] == "FillRecorded"]
    assert len(fills) == 2
