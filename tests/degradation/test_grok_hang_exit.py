"""GRK-07: a hung x.ai transport cannot delay a protective exit sell.

The exit engine (``LedgerExitBook`` and ``PositionWatcher``, which ``ExitRules``
wraps) and a real ``GrokGateway`` admission share one event loop. The Grok
transport never returns. Each test requires the stop-loss sell to complete
while the Grok call is still pending, and before the Grok deadline on the
injected clock. The second case first holds every in-flight slot with hung calls.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

from pumpgrok.config.settings import ExitsSettings
from pumpgrok.engine.models import PRICE_SCALE, ExitPosition
from pumpgrok.engine.watcher import PositionWatcher
from pumpgrok.grok.budget import LayeredBudget
from pumpgrok.grok.cache import ResponseCache
from pumpgrok.grok.gateway import (
    MAX_INFLIGHT,
    TRANSPORT_DEADLINE_S,
    Candidate,
    GrokGateway,
    GrokOutcome,
    GrokRequest,
)
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.supervisor.exit_rules import LedgerExitBook

START = 1_800_000_000.0
MINT = "HungExitMint1111111111111111111111111111111"
ENTRY = Decimal("100")
CRASHED_PRICE = Decimal("60")
CFG = ExitsSettings(
    stop_loss_pct=30.0,
    take_profit_pct=120.0,
    trailing_stop_pct=35.0,
    max_hold_seconds=3600.0,
    stop_loss_poll_seconds=15.0,
)


class HungTransport:
    """Holds every call open until the test cancels it. It never answers."""

    def __init__(self) -> None:
        self.started = 0
        self._never = asyncio.Event()

    async def __call__(self, _request: GrokRequest, _text: str) -> str:
        self.started += 1
        await self._never.wait()
        raise AssertionError("a hung transport must be cancelled, not answered")


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", "1000000")
    store.set_meta("source", "paper")
    return store


def _open_position(store: LedgerStore, clock: FixtureClock) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key="open|hung",
        type="PositionOpened",
        payload={
            "source": "paper",
            "mint": MINT,
            "price_entry": str(ENTRY),
            "token_units": 10,
            "cost_basis_lamports": 1000,
            "opened_ts_utc": format_ts_utc(clock.now()),
            "ticket_id": "tick-hung",
        },
    )


def _gateway(tmp_path: Path, clock: FixtureClock, transport: HungTransport) -> GrokGateway:
    return GrokGateway(
        clock=clock,
        transport=transport,
        cache=ResponseCache(tmp_path / "cache.sqlite", clock),
        budget=LayeredBudget(tmp_path / "budget.sqlite", clock),
    )


def _request(index: int) -> GrokRequest:
    return GrokRequest(
        event_id=f"narrative-{index}",
        agent="narrative",
        model="grok-test",
        prompt_sha="d" * 64,
        schema="verdict.v1",
        input={"mint": MINT},
        text=f"hung market {index}",
        candidate=Candidate(
            mint=MINT,
            created_at=START - 600,
            first_trade_at=START - 300,
            unique_buyers=9,
            prerank=Decimal("0.8"),
            last_decision_at=None,
        ),
    )


async def _settle(rounds: int = 10) -> None:
    for _ in range(rounds):
        await asyncio.sleep(0)


async def _stop_loss_pass(store: LedgerStore, clock: FixtureClock) -> list[tuple[str, str, float]]:
    """One real exit pass at a crashed price. Returns (mint, reason, virtual time) per sell."""
    book = LedgerExitBook(CFG)
    book.sync(store)
    sold: list[tuple[str, str, float]] = []

    async def price_fn(_mint: str) -> int:
        return int(CRASHED_PRICE * PRICE_SCALE)

    async def sell_fn(position: ExitPosition, _price: int, reason: str) -> None:
        sold.append((position.mint, reason, clock.now()))

    watcher = PositionWatcher(book, price_fn, sell_fn, clock)
    await asyncio.wait_for(watcher.check_once(START + 60.0), timeout=1.0)
    return sold


async def test_stop_loss_sells_while_a_hung_grok_call_is_pending(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        _open_position(store, clock)
        transport = HungTransport()
        gateway = _gateway(tmp_path, clock, transport)
        pending = asyncio.create_task(gateway.admit(_request(0)))
        await _settle()
        assert transport.started == 1

        sold = await _stop_loss_pass(store, clock)

        assert [(mint, reason) for mint, reason, _ in sold] == [(MINT, "stop_loss")]
        assert sold[0][2] < START + TRANSPORT_DEADLINE_S, "sell must not wait for the deadline"
        assert not pending.done()

        clock.advance_to(START + TRANSPORT_DEADLINE_S)
        outcome: GrokOutcome = await asyncio.wait_for(pending, timeout=1.0)
        assert outcome.status == "rule_fallback"
        assert outcome.reason == "timeout"
    finally:
        store.close()


async def test_stop_loss_sells_when_every_grok_slot_is_held_by_a_hung_call(
    tmp_path: Path,
) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        _open_position(store, clock)
        transport = HungTransport()
        gateway = _gateway(tmp_path, clock, transport)
        pending = [
            asyncio.create_task(gateway.admit(_request(index)))
            for index in range(MAX_INFLIGHT + 2)
        ]
        await _settle()
        assert transport.started == MAX_INFLIGHT

        sold = await _stop_loss_pass(store, clock)

        assert [(mint, reason) for mint, reason, _ in sold] == [(MINT, "stop_loss")]
        # Requests the minute budget refuses finish at once; the slot holders stay pending.
        assert sum(not task.done() for task in pending) >= MAX_INFLIGHT

        clock.advance_to(START + TRANSPORT_DEADLINE_S)
        await _settle()
        clock.advance_to(START + 2 * TRANSPORT_DEADLINE_S)
        outcomes = await asyncio.wait_for(asyncio.gather(*pending), timeout=1.0)
        assert all(outcome.response is None for outcome in outcomes)
    finally:
        store.close()
