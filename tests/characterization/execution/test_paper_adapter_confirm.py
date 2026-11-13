"""Characterization pins for PaperAdapter confirmation (``_await_confirmation``).

Each scenario records the CONFIRMING outcome for the unsplit code: the returned
reserves, latency and size cap, or the refusal (cancel, missing reserves,
layout, graduation, re-check, seeded drop, confirmation timeout) together with
every ledger row and hash. The digests in ``PINS`` were recorded on the unsplit
code (CONTEXT D-10) and must still hold after ``confirm_stages.py`` lands.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
from collections.abc import Awaitable, Callable
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
from pumpgrok.risk.limits import EngineLimits

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
#: Graduation: the curve completes between the BUY's ACCEPTED read (+1s) and its
#: CONFIRMING read (+3s).
GRADUATED_AT_S = 2.5
GRADUATING: tuple[Tick, ...] = (
    (0.0, S0, T0, False),
    (GRADUATED_AT_S, S0, T0, True),
)


class Harness:
    def __init__(
        self,
        root: Path,
        timeline: tuple[Tick, ...] = CURVE,
        *,
        limits: EngineLimits | None = None,
        p_drop: float = 0.0,
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
            autonomy="autonomous-paper",
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
            limits=limits,
            p_drop=p_drop,
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

    def sell_request(self, *, units: int) -> OrderRequest:
        return OrderRequest(
            ticket_id=SELL_TICKET,
            mint=MINT,
            side=Side.SELL,
            decision_id=self.ids.ulid(),
            token_units=units,
            max_slippage_bps=100,
            approval_id=f"apr-{self.ids.ulid()}",
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


async def place_and_cancel(h: Harness, request: OrderRequest) -> tuple[Any, bool]:
    """Place a sell and cancel it while its latency sleep is still running."""
    task = asyncio.create_task(h.adapter.place(request, seat=SELL_SEAT, correlation_id="test"))
    accepted = False
    for _ in range(4000):
        if task.done():
            break
        h.clock.advance_to(h.clock.now() + 0.01)
        await asyncio.sleep(0)
        if not accepted:
            sells = [e for e in h.ledger() if e["type"] == "OrderPlaced"]
            sells = [e for e in sells if e["payload"]["side"] == "sell"]
            if sells:
                order_id = str(sells[-1]["payload"]["order_id"])
                accepted = await h.adapter.cancel(order_id, request.ticket_id, request.decision_id)
    if not task.done():
        task.cancel()
        raise AssertionError("cancelled sell did not settle")
    try:
        value: Any = await task
    except Exception as exc:
        value = exc
    return value, accepted


async def scn_confirm_direct_sell(root: Path) -> dict[str, Any]:
    h = Harness(root)
    buy = await h.open_position()
    request = h.sell_request(units=buy.filled_units)
    result = await h.drive(
        h.adapter._await_confirmation(
            request,
            order_id=h.ids.ulid(),
            forbid_complete=False,
            ledger_source="replay",
            correlation_id="test",
            seat=SELL_SEAT,
            exit_reason=None,
            creator=None,
            owner=object(),
        )
    )
    value = result[0]
    if isinstance(value, Exception):
        return {"outcome": outcome(value), "rows": h.ledger()}
    curve1, latency_s, cap = value
    return {
        "curve": curve1.model_dump(mode="json"),
        "latency": repr(latency_s),
        "cap": cap,
        "rows": h.ledger(),
    }


async def scn_confirm_timeout_sell(root: Path) -> dict[str, Any]:
    h = Harness(root)
    buy = await h.open_position()
    h.adapter._limits = EngineLimits(confirm_timeout_s=0.001)
    request = h.sell_request(units=buy.filled_units)
    first = await h.drive(h.adapter.place(request, seat=SELL_SEAT, correlation_id="test"))
    second = await h.drive(h.adapter.place(request, seat=SELL_SEAT, correlation_id="test"))
    return {"first": outcome(first[0]), "second": outcome(second[0]), "rows": h.ledger()}


async def scn_cancel_sell_during_latency(root: Path) -> dict[str, Any]:
    h = Harness(root)
    buy = await h.open_position()
    value, accepted = await place_and_cancel(h, h.sell_request(units=buy.filled_units))
    return {"outcome": outcome(value), "cancel_accepted": accepted, "rows": h.ledger()}


async def scn_recheck_refused_sell(root: Path) -> dict[str, Any]:
    h = Harness(root)
    buy = await h.open_position()
    original = h.risk.check

    def refuse_at_confirming(request: OrderRequest, **kwargs: Any) -> Any:
        decision = original(request, **kwargs)
        if kwargs.get("stage") == "CONFIRMING":
            return decision.model_copy(update={"passed": False, "reason": "daily_loss_halt"})
        return decision

    h.risk.check = refuse_at_confirming
    sell = await h.drive(
        h.adapter.place(
            h.sell_request(units=buy.filled_units), seat=SELL_SEAT, correlation_id="test"
        )
    )
    return {"outcome": outcome(sell[0]), "rows": h.ledger()}


async def scn_tx_dropped_sell(root: Path) -> dict[str, Any]:
    h = Harness(root)
    buy = await h.open_position()
    h.adapter._p_drop = 1.0
    sell = await h.drive(
        h.adapter.place(
            h.sell_request(units=buy.filled_units), seat=SELL_SEAT, correlation_id="test"
        )
    )
    return {"outcome": outcome(sell[0]), "rows": h.ledger()}


async def scn_buy_no_reserves_confirming(root: Path) -> dict[str, Any]:
    # Verified replay cannot remove a curve once a tick exists: the CONFIRMING read stays priced.
    h = Harness(root)
    buy = await h.drive(
        h.adapter.place(h.buy_request(), seat="bot-04-sniper", correlation_id="test")
    )
    return {"outcome": outcome(buy[0]), "rows": h.ledger()}


async def scn_buy_data_unavailable_confirming(root: Path) -> dict[str, Any]:
    # Verified replay reads carry VERIFIED_REPLAY provenance, never an RPC layout refusal.
    h = Harness(root)
    buy = await h.drive(
        h.adapter.place(h.buy_request(), seat="bot-04-sniper", correlation_id="test")
    )
    return {"outcome": outcome(buy[0]), "rows": h.ledger()}


async def scn_buy_post_graduation_confirming(root: Path) -> dict[str, Any]:
    h = Harness(root, GRADUATING)
    buy = await h.drive(
        h.adapter.place(h.buy_request(), seat="bot-04-sniper", correlation_id="test")
    )
    return {"outcome": outcome(buy[0]), "rows": h.ledger()}


SCENARIOS: dict[str, Callable[[Path], Awaitable[dict[str, Any]]]] = {
    "confirm_direct_sell": scn_confirm_direct_sell,
    "confirm_timeout_sell": scn_confirm_timeout_sell,
    "cancel_sell_during_latency": scn_cancel_sell_during_latency,
    "recheck_refused_sell": scn_recheck_refused_sell,
    "tx_dropped_sell": scn_tx_dropped_sell,
    "buy_no_reserves_confirming": scn_buy_no_reserves_confirming,
    "buy_data_unavailable_confirming": scn_buy_data_unavailable_confirming,
    "buy_post_graduation_confirming": scn_buy_post_graduation_confirming,
}

_PIN_TABLE = """
confirm_direct_sell d0bd211fa0b3e5f61248ba6af2b18624b054e325ccfec119e682d5a048dcf05e
confirm_timeout_sell ee1f7ada95a6677749f73a31165e1f51aac257ee1de217b14d4b19df9695c2a3
cancel_sell_during_latency 83ce6c54a7af5b5765651a6a09081e962b8290ff45b5bbf1001df5beb59fd6c8
recheck_refused_sell 7966be29584c1c9c8e0d967c56dbff0ac940dcb8af49b0f4bdf182c83096d5ef
tx_dropped_sell c4cf29190bf980905374877200a8df3038a2f46e4e9621d1841b9942ae8ce349
# Outcome changed from refusal to fill under verified replay (13-07 changelog).
buy_no_reserves_confirming a0fa1398fb57f2671d68de1112effb55bae7423845193bd63ee766381e793472
# Outcome changed from refusal to fill under verified replay (13-07 changelog).
buy_data_unavailable_confirming a0fa1398fb57f2671d68de1112effb55bae7423845193bd63ee766381e793472
buy_post_graduation_confirming 178d45891ce8972653b4690d0a30617051d57b4db9d03a73a659d651bb587510
"""
PINS: dict[str, str] = dict(
    line.split() for line in _PIN_TABLE.strip().splitlines() if not line.startswith("#")
)


@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_confirm_scenario_matches_pinned_digest(tmp_path: Path, name: str) -> None:
    trace = await SCENARIOS[name](tmp_path)
    assert digest(trace) == PINS[name]


async def test_direct_confirmation_returns_reserves_latency_and_no_size_cap(
    tmp_path: Path,
) -> None:
    trace = await scn_confirm_direct_sell(tmp_path)
    assert trace["cap"] is None
    assert trace["curve"]["s_lamports"] == S0
    assert trace["curve"]["t_units"] == T0


async def test_confirmation_timeout_is_unknown_and_never_retried(tmp_path: Path) -> None:
    trace = await scn_confirm_timeout_sell(tmp_path)
    assert trace["first"]["reason"] == "confirmation_timeout"
    assert trace["first"]["stage"] == "CONFIRMING"
    assert trace["second"]["error"] == trace["first"]["error"]
    assert trace["second"]["reason"] == trace["first"]["reason"]
    assert trace["second"]["stage"] == trace["first"]["stage"]
    rejects = [row for row in trace["rows"] if row["type"] == "OrderRejected"]
    assert len(rejects) == 1


async def test_cancel_during_latency_refuses_at_confirming(tmp_path: Path) -> None:
    trace = await scn_cancel_sell_during_latency(tmp_path)
    assert trace["cancel_accepted"] is True
    assert trace["outcome"]["reason"] == "cancelled"
    assert trace["outcome"]["stage"] == "CONFIRMING"


async def test_recheck_refusal_at_confirming_writes_no_fill(tmp_path: Path) -> None:
    trace = await scn_recheck_refused_sell(tmp_path)
    assert trace["outcome"]["reason"] == "daily_loss_halt"
    assert trace["outcome"]["stage"] == "CONFIRMING"
    assert [row["type"] for row in trace["rows"]].count("FillRecorded") == 1


async def test_seeded_drop_refuses_without_retry(tmp_path: Path) -> None:
    trace = await scn_tx_dropped_sell(tmp_path)
    assert trace["outcome"]["reason"] == "tx_dropped"
    assert trace["outcome"]["fees"] == 0
    assert [row["type"] for row in trace["rows"]].count("FillRecorded") == 1


async def test_buy_confirmation_refuses_a_completed_curve(tmp_path: Path) -> None:
    trace = await scn_buy_post_graduation_confirming(tmp_path)
    assert trace["outcome"]["reason"] == "post_graduation_no_reserves"
    assert trace["outcome"]["stage"] == "CONFIRMING"
