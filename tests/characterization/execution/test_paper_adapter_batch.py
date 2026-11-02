"""Characterization pins for PaperAdapter ledger batches (``_append_order_batch``).

Each scenario records the outcome and every ledger row, hash included, for the
unsplit batch writer: the consume and OrderPlaced rows, risk refusals at
ACCEPTED, the consumed-approval collision and the repeat replay. The digests in
``PINS`` were recorded on the unsplit code (CONTEXT D-10) and must still hold
after ``batch_stages.py`` lands.
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

from pumpgrok.core.adapter import Fill, OrderRequest, Side
from pumpgrok.core.errors import OrderRejectedError
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.paper_adapter import CurveSnapshot, PaperAdapter
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


class Curves:
    """Pop one scripted snapshot per read; hold the last."""

    def __init__(self, reads: list[CurveSnapshot | None]) -> None:
        self.reads = list(reads)

    async def curve(self, mint: str) -> CurveSnapshot | None:
        if len(self.reads) > 1:
            return self.reads.pop(0)
        return self.reads[0]


def snap(s: int, t: int) -> CurveSnapshot:
    return CurveSnapshot(mint=MINT, s_lamports=s, t_units=t)


class Harness:
    def __init__(
        self,
        root: Path,
        reads: list[CurveSnapshot | None],
        *,
        autonomy: str = "autonomous-paper",
        seed: int = 7,
    ) -> None:
        self.clock = FixtureClock(START)
        self.store = LedgerStore(str(root / "ledger.sqlite"))
        self.store.set_meta("initial_equity_lamports", str(EQUITY))
        self.store.set_meta("source", "paper")
        self.ids = IdFactory(self.clock, make_rng(seed))
        self.curves = Curves(reads)
        budget = RiskBudget()
        self.risk = RiskEngine(
            store=self.store,
            budget=budget,
            ids=IdFactory(self.clock, random.Random(seed)),
            clock=self.clock,
            autonomy=autonomy,
            get_reserves=lambda _mint: (S0, T0),
        )
        self.adapter = PaperAdapter(
            store=self.store,
            risk=self.risk,
            ids=self.ids,
            clock=self.clock,
            rng=make_rng(seed),
            budget=budget,
            price_source=self.curves,
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

    def sell_request(self, *, units: int, exit_reason: str | None = None) -> OrderRequest:
        return OrderRequest(
            ticket_id=SELL_TICKET,
            mint=MINT,
            side=Side.SELL,
            decision_id=self.ids.ulid(),
            token_units=units,
            max_slippage_bps=100,
            approval_id=f"apr-{self.ids.ulid()}",
            exit_reason=exit_reason,
            correlation_id="test",
        )

    async def open_position(self) -> Fill:
        self.curves.reads = [snap(S0, T0)]
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
    return {"returned": repr(value)}


def digest(trace: dict[str, Any]) -> str:
    text = json.dumps(trace, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


async def scn_buy_order_placed(root: Path) -> dict[str, Any]:
    h = Harness(root, [snap(S0, T0)])
    h.curves.reads = [snap(S0, T0)]
    buy = await h.drive(
        h.adapter.place(h.buy_request(), seat="bot-04-sniper", correlation_id="test")
    )
    return {"outcome": outcome(buy[0]), "rows": h.ledger()}


async def scn_sell_rule_exit_consumes_approval(root: Path) -> dict[str, Any]:
    h = Harness(root, [snap(S0, T0)])
    buy = await h.open_position()
    h.curves.reads = [snap(S0, T0), snap(S0, T0)]
    request = h.sell_request(units=buy.filled_units, exit_reason="stop_loss")
    sell = await h.drive(h.adapter.place(request, seat=SELL_SEAT, correlation_id="test"))
    return {"outcome": outcome(sell[0]), "rows": h.ledger()}


async def scn_sell_wrong_seat_refused_then_replayed(root: Path) -> dict[str, Any]:
    h = Harness(root, [snap(S0, T0)])
    buy = await h.open_position()
    h.curves.reads = [snap(S0, T0)]
    request = h.sell_request(units=buy.filled_units)
    first = await h.drive(h.adapter.place(request, seat="bot-04-sniper", correlation_id="test"))
    second = await h.drive(h.adapter.place(request, seat="bot-04-sniper", correlation_id="test"))
    return {"first": outcome(first[0]), "second": outcome(second[0]), "rows": h.ledger()}


async def scn_consumed_approval_collision(root: Path) -> dict[str, Any]:
    h = Harness(root, [snap(S0, T0)])
    buy = await h.open_position()
    h.curves.reads = [snap(S0, T0)]
    original = h.store.append_batch

    def collide(rows: Any) -> Any:
        # Another order consumed this approval first: the consume key already exists.
        for row in rows:
            key = str(row["idempotency_key"])
            if key.startswith("consume|"):
                h.store.append(
                    ts_utc=str(row["ts_utc"]),
                    source=str(row["source"]),
                    correlation_id=str(row["correlation_id"]),
                    idempotency_key=key,
                    type=str(row["type"]),
                    payload=dict(row["payload"]),
                )
        return original(rows)

    h.store.append_batch = collide
    request = h.sell_request(units=buy.filled_units, exit_reason="stop_loss")
    sell = await h.drive(h.adapter.place(request, seat=SELL_SEAT, correlation_id="test"))
    return {"outcome": outcome(sell[0]), "rows": h.ledger()}


async def scn_direct_append_order_batch(root: Path) -> dict[str, Any]:
    h = Harness(root, [snap(S0, T0)])
    buy = await h.open_position()
    request = h.sell_request(units=buy.filled_units, exit_reason="take_profit")
    order_id = h.ids.ulid()
    quote_id = h.ids.ulid()
    written = await h.drive(
        h.adapter._append_order_batch(
            request,
            order_id=order_id,
            quote_id=quote_id,
            out0=1_000_000,
            threshold=990_000,
            impact=Decimal("0.0125"),
            ledger_source="paper",
            correlation_id="test",
            seat=SELL_SEAT,
            exit_reason="take_profit",
            creator=None,
        )
    )
    return {"outcome": outcome(written[0]), "rows": h.ledger()}


async def scn_direct_append_order_batch_duplicate(root: Path) -> dict[str, Any]:
    h = Harness(root, [snap(S0, T0)])
    buy = await h.open_position()
    request = h.sell_request(units=buy.filled_units, exit_reason="take_profit")
    order_id = h.ids.ulid()
    quote_id = h.ids.ulid()
    kwargs: dict[str, Any] = {
        "order_id": order_id,
        "quote_id": quote_id,
        "out0": 1_000_000,
        "threshold": 990_000,
        "impact": Decimal("0.0125"),
        "ledger_source": "paper",
        "correlation_id": "test",
        "seat": SELL_SEAT,
        "exit_reason": "take_profit",
        "creator": None,
    }
    first = await h.drive(h.adapter._append_order_batch(request, **kwargs))
    second = await h.drive(h.adapter._append_order_batch(request, **kwargs))
    return {"first": outcome(first[0]), "second": outcome(second[0]), "rows": h.ledger()}


SCENARIOS: dict[str, Callable[[Path], Awaitable[dict[str, Any]]]] = {
    "buy_order_placed": scn_buy_order_placed,
    "sell_rule_exit_consumes": scn_sell_rule_exit_consumes_approval,
    "sell_wrong_seat_replayed": scn_sell_wrong_seat_refused_then_replayed,
    "consumed_approval_collision": scn_consumed_approval_collision,
    "direct_append_order_batch": scn_direct_append_order_batch,
    "direct_batch_duplicate": scn_direct_append_order_batch_duplicate,
}

_PIN_TABLE = """
buy_order_placed 684fdc433a6141f8d4cc2177504fb684d568ce3214df9007dd748ca5e7c0c9bf
sell_rule_exit_consumes 1ace216d40c7b7340a8bbe697564aaa278dd78212ccbd8f205005379b509b05f
sell_wrong_seat_replayed 3500e284433e50b6d01098b05389a1d4dd25b671a82307f75c0ec32c1514e7e2
consumed_approval_collision 35830f04d4344a52a1802a9369df433350f6919a7572e203783aca7934546df6
direct_append_order_batch 3c81b0c6d469504494e929ab506067a68a444ffbd73cb27a036e5a5d267082d2
direct_batch_duplicate 7b7e7581c42857ff15857e6d95a3c3edcbb9fbe622c1bf6fd077d15bc7d49e47
"""
PINS: dict[str, str] = dict(line.split() for line in _PIN_TABLE.strip().splitlines())


@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_batch_scenario_matches_pinned_digest(tmp_path: Path, name: str) -> None:
    trace = await SCENARIOS[name](tmp_path)
    assert digest(trace) == PINS[name]


async def test_rule_exit_writes_consume_row_before_order_placed(tmp_path: Path) -> None:
    trace = await scn_sell_rule_exit_consumes_approval(tmp_path)
    kinds = [row["type"] for row in trace["rows"]]
    last_placed = len(kinds) - 1 - kinds[::-1].index("OrderPlaced")
    assert kinds[last_placed - 1] == "ApprovalRecorded"


async def test_wrong_seat_sell_refuses_and_replays_the_first_refusal(tmp_path: Path) -> None:
    trace = await scn_sell_wrong_seat_refused_then_replayed(tmp_path)
    assert trace["first"]["stage"] == "ACCEPTED"
    assert trace["second"]["reason"] == trace["first"]["reason"]
    assert trace["second"]["stage"] == trace["first"]["stage"]
    rejects = [row for row in trace["rows"] if row["type"] == "OrderRejected"]
    assert len(rejects) == 1


async def test_consumed_approval_refuses_the_whole_batch(tmp_path: Path) -> None:
    trace = await scn_consumed_approval_collision(tmp_path)
    assert trace["outcome"]["reason"] == "approval_missing"
    assert trace["outcome"]["stage"] == "ACCEPTED"
    kinds = [row["type"] for row in trace["rows"]]
    assert kinds.count("OrderPlaced") == 1
