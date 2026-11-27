"""Unit checks for event-driven seat cycle bodies (EVT-10, 14-03/14-04).

Each body is exercised through :func:`build_event_cycles` parts with small
fakes: a fake ledger, curve source, risk engine and trading wiring. Bodies
must skip, withhold or degrade honestly on timer starts and non-candidate
events instead of inventing observations.
"""

from __future__ import annotations

import asyncio
import random
from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel

from pumpgrok.config.sections.engine import FilterSettings
from pumpgrok.core.ids import IdFactory
from pumpgrok.events.models import Event, EventKind
from pumpgrok.execution.paper_adapter.models import CurveSnapshot
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.scheduler import event_cycles
from pumpgrok.supervisor.scheduler.degraded import DegradedState
from pumpgrok.supervisor.scheduler.supervisor import TRIGGER_EVENT
from pumpgrok.supervisor.seat_task import SeatContext

MINT = "Mint11111111111111111111111111111111111111111"


class FakeStore:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    def read(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return list(self._rows)


class FakeCurves:
    def __init__(self, snapshot: CurveSnapshot | None = None) -> None:
        self._snapshot = snapshot

    async def curve(self, mint: str) -> CurveSnapshot | None:
        return self._snapshot


def _ctx(**overrides: Any) -> SeatContext:
    kwargs: dict[str, Any] = {
        "seat_id": "bot-01-scout",
        "clock": FixtureClock(),
        "rng": random.Random(7),
        "store": FakeStore(),
    }
    kwargs.update(overrides)
    return SeatContext(**kwargs)


def _event(kind: EventKind, **overrides: Any) -> Event:
    kwargs: dict[str, Any] = {
        "kind": kind,
        "entity_id": MINT,
        "payload": {"name": "TestCoin"},
        "occurred_at": "2026-01-01T00:00:00Z",
    }
    kwargs.update(overrides)
    return Event(**kwargs)


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_chief_reports_kill_switch_latch() -> None:
    store = FakeStore([{"type": "KillSwitchSet"}])
    result = _run(event_cycles._chief(_ctx(store=store), store=store))  # type: ignore[arg-type]
    assert result["kill_switch"] is True
    assert result["trigger"] == "timer"


def test_scout_skips_without_an_event() -> None:
    TOKEN = TRIGGER_EVENT.set(None)
    try:
        result = _run(event_cycles._scout(_ctx(), curves=FakeCurves(), filter_cfg=FilterSettings()))
    finally:
        TRIGGER_EVENT.reset(TOKEN)
    assert result == {"mint": None, "decision": "skip", "reason": "no_event", "trigger": "timer"}


def test_scout_skips_a_migration() -> None:
    TOKEN = TRIGGER_EVENT.set(_event(EventKind.migration))
    try:
        result = _run(event_cycles._scout(_ctx(), curves=FakeCurves(), filter_cfg=FilterSettings()))
    finally:
        TRIGGER_EVENT.reset(TOKEN)
    assert result["decision"] == "skip"
    assert result["reason"] == "not_a_new_token"
    assert result["trigger"] == "migration"


def test_scout_reports_no_curve() -> None:
    TOKEN = TRIGGER_EVENT.set(_event(EventKind.token_created))
    try:
        result = _run(
            event_cycles._scout(_ctx(), curves=FakeCurves(None), filter_cfg=FilterSettings())
        )
    finally:
        TRIGGER_EVENT.reset(TOKEN)
    assert result["reason"] == "no_curve"
    assert result["mint"] == MINT


def test_scout_verdict_carries_trigger() -> None:
    snapshot = CurveSnapshot(mint=MINT, s_lamports=30_000_000_000, t_units=10**15, complete=False)
    TOKEN = TRIGGER_EVENT.set(_event(EventKind.token_created))
    try:
        result = _run(
            event_cycles._scout(_ctx(), curves=FakeCurves(snapshot), filter_cfg=FilterSettings())
        )
    finally:
        TRIGGER_EVENT.reset(TOKEN)
    assert result["mint"] == MINT
    assert result["trigger"] == "token_created"
    assert result["decision"] in ("skip", "buy")


def test_risk_reports_halt_verdict() -> None:
    risk = SimpleNamespace(evaluate_halts=lambda source, correlation_id: "halt:drawdown")
    trading = SimpleNamespace(refresh_marks=None)
    result = _run(event_cycles._risk(_ctx(), risk=risk, trading=trading))  # type: ignore[arg-type]
    assert result == {"halt": "halt:drawdown", "trigger": "timer"}


def test_rug_blind_unread_readable() -> None:
    TOKEN = TRIGGER_EVENT.set(_event(EventKind.token_created))
    try:
        blind = _run(
            event_cycles._rug(
                _ctx(), degraded=DegradedState(rpc_endpoints=[False]), curves=FakeCurves()
            )
        )
        unread = _run(
            event_cycles._rug(
                _ctx(), degraded=DegradedState(rpc_endpoints=[True]), curves=FakeCurves(None)
            )
        )
        snapshot = CurveSnapshot(mint=MINT, s_lamports=30_000_000_000, t_units=10**15)
        readable = _run(
            event_cycles._rug(
                _ctx(),
                degraded=DegradedState(rpc_endpoints=[True]),
                curves=FakeCurves(snapshot),
            )
        )
    finally:
        TRIGGER_EVENT.reset(TOKEN)
    assert blind["verdict"] == "BLIND"
    assert unread["verdict"] == "UNREAD"
    assert readable["verdict"] == "READABLE"


def test_sniper_withholds_and_skips_honestly() -> None:
    trading = SimpleNamespace(refresh_marks=None)
    TOKEN = TRIGGER_EVENT.set(_event(EventKind.kill_switch))
    try:
        withheld = _run(event_cycles._sniper(_ctx(), trading=trading))  # type: ignore[arg-type]
        TRIGGER_EVENT.set(_event(EventKind.token_created))
        not_intent = _run(event_cycles._sniper(_ctx(), trading=trading))  # type: ignore[arg-type]
        TRIGGER_EVENT.set(_event(EventKind.strategy_intent))
        observe = _run(
            event_cycles._sniper(
                _ctx(observe_only=True),
                trading=trading,  # type: ignore[arg-type]
            )
        )
    finally:
        TRIGGER_EVENT.reset(TOKEN)
    assert withheld["withheld"] == "kill_switch"
    assert not_intent["reason"] == "not_an_intent"
    assert observe["observe_only"] is True


def test_exit_observe_only_counts_open_positions() -> None:
    store = FakeStore([{"type": "PositionOpened"}, {"type": "PositionOpened"}])
    trading = SimpleNamespace(refresh_marks=None)
    result = _run(
        event_cycles._exit(_ctx(store=store, observe_only=True), store=store, trading=trading)  # type: ignore[arg-type]
    )
    assert result["open"] == 2
    assert result["rule_sells"] == 0


def test_merge_refuses_a_seat_no_event_wakes() -> None:
    try:
        event_cycles.merge_event_cycles({}, {"bot-07-shill": lambda ctx: None})
    except ValueError as exc:
        assert "bot-07-shill" in str(exc)
    else:
        raise AssertionError("merge accepted a seat no event wakes")


def test_degraded_state_rpc_blind_needs_all_endpoints_down() -> None:
    assert DegradedState().rpc_blind is False
    assert DegradedState(rpc_endpoints=[False]).rpc_blind is True
    assert DegradedState(rpc_endpoints=[False, True]).rpc_blind is False


def test_sniper_places_one_buy_on_an_intent() -> None:

    class _Input(BaseModel):
        ticket_id: str
        mint: str
        side: str
        decision_id: str
        size_lamports: int
        max_slippage_bps: int
        approval_id: str

    seen: list[Any] = []

    class _Place:
        spec = SimpleNamespace(input_model=_Input)

        async def __call__(self, payload: Any) -> Any:
            seen.append(payload)
            return SimpleNamespace(
                model_dump=lambda mode="json": {"status": "filled", "reason": "ok"}
            )

    clock = FixtureClock()
    trading = SimpleNamespace(
        refresh_marks=None,
        ids=IdFactory(clock, random.Random(3)),
        place=_Place(),
        clock=clock,
        store=None,
        attempts=[],
    )
    TOKEN = TRIGGER_EVENT.set(_event(EventKind.strategy_intent))
    try:
        result = _run(event_cycles._sniper(_ctx(), trading=trading))  # type: ignore[arg-type]
    finally:
        TRIGGER_EVENT.reset(TOKEN)
    assert result["orders"] == 1
    assert result["status"] == "filled"
    assert result["trigger"] == "strategy_intent"
    assert len(seen) == 1
    assert len(trading.attempts) == 1
