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
sell_full_close a0b768a7a5c12cb39f8790e39998cc80d31a56c55971943dbdb7243c4cffc648
sell_partial_over_holding d8d819cd2606ec912472fecc7db111025f5366e7cf6612ed60d1408fbd65e479
sell_size_based d260211fd63b1aca2100436b534e3f17e1f4a04d92f1ae160dfb2fa31915cefd
sell_no_position 8ad27ed745c5e77f54f5cc1a41c86a6d6e9984bbd00b2fba3fb05a676c07a288
sell_below_liquidity_floor 6b558398c6b9a2a15843374e1da0ee4d0d584d8d3ba2d60942f9fa3458962f85
# Outcome changed from refusal to fill under verified replay (13-07 changelog).
sell_no_reserves_accepted a0b768a7a5c12cb39f8790e39998cc80d31a56c55971943dbdb7243c4cffc648
sell_slippage_confirming 48dfd097203d4e2f8f4f899a5e6f36c8f22099813f6d930b79a04d4596464566
# Outcome changed from refusal to fill under verified replay (13-07 changelog).
sell_no_reserves_confirming a0b768a7a5c12cb39f8790e39998cc80d31a56c55971943dbdb7243c4cffc648
sell_concurrent_confirming 4fc28e6c06759535a15c2c621946035b0bd68d785a17620f69868d8beae9c109
sell_repeat_replays_fill 706c82ac6451d991f00b03ecf319592df7d8298471fac11f7a1876e699488946
sell_direct_place_sell a0b768a7a5c12cb39f8790e39998cc80d31a56c55971943dbdb7243c4cffc648
"""
PINS: dict[str, str] = dict(
    line.split() for line in _PIN_TABLE.strip().splitlines() if not line.startswith("#")
)


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
