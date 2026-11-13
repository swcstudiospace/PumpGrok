"""Trading and safety seat cycles bound to bus events (EVT-10, 14-04 slice A).

Events go through the real EventBus; its handler is the supervisor's ``on_event``. Every seat
cycle is wrapped by a spy that records the event the cycle saw and what it returned. The runtime
is the offline fixture sandbox: no network, no wall clock, injected virtual time only.
"""

from __future__ import annotations

import ast
import asyncio
import subprocess
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.config.settings import FilterSettings
from pumpgrok.events.bus import EventBus
from pumpgrok.events.constants import P2_DEBOUNCE_S
from pumpgrok.events.models import Event, EventKind, FrozenPayload
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import parse_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.supervisor.scheduler import ROSTER, Supervisor, open_replay_runtime
from pumpgrok.supervisor.scheduler.degraded import DegradedState
from pumpgrok.supervisor.scheduler.event_cycles import build_event_cycles
from pumpgrok.supervisor.scheduler.orders import _replay_trading
from pumpgrok.supervisor.scheduler.replay_cycles import _replay_cycles
from pumpgrok.supervisor.scheduler.replay_runtime import ReplayRuntime, _ReplayTrading
from pumpgrok.supervisor.scheduler.supervisor import TRIGGER_EVENT
from pumpgrok.supervisor.scheduler.wake import EVENT_CYCLE_SEATS, SEAT_WAKES, wake_order

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "tests" / "fixtures" / "replay" / "smoke"
EVENT_CYCLES = REPO / "src" / "pumpgrok" / "supervisor" / "scheduler" / "event_cycles.py"
SEED = 20260101
#: Pre-graduation mint with a curve read at 00:00:01.250Z (fixture S = 42.35e9 lamports).
MINT_A = "SmokeMintAAAA1111111111111111111111111111111"
TICK_A = "2026-01-01T00:00:01.250Z"

CHIEF = "bot-00-chief"
SCOUT = "bot-01-scout"
RISK = "bot-02-risk"
SNIPER = "bot-04-sniper"
RUG = "bot-05-rug"
EXIT = "bot-06-exit"
SIX = (CHIEF, SCOUT, RISK, SNIPER, RUG, EXIT)

Seen = tuple[str, str | None, dict[str, Any]]


@dataclass
class Harness:
    runtime: ReplayRuntime
    trading: _ReplayTrading
    supervisor: Supervisor
    bus: EventBus
    seen: list[Seen] = field(default_factory=list)
    dlq: list[Event] = field(default_factory=list)

    @property
    def store(self) -> LedgerStore:
        return self.runtime.store


def _spy(
    seat: str, cycle: Callable[[Any], Awaitable[Any]], seen: list[Seen]
) -> Callable[[Any], Awaitable[Any]]:
    """Record the event the cycle saw and its result; errors are recorded then re-raised."""

    async def _run(ctx: Any) -> Any:
        trigger = TRIGGER_EVENT.get()
        kind = None if trigger is None else trigger.kind.value
        try:
            result = await cycle(ctx)
        except BaseException as exc:
            seen.append((seat, kind, {"error": repr(exc)}))
            raise
        seen.append((seat, kind, dict(result or {})))
        return result

    return _run


async def _open(tmp_path: Path, *, at: str | None = TICK_A) -> Harness:
    runtime = open_replay_runtime(SMOKE, FilterSettings(), seed=SEED, ledger_path=tmp_path / "l.db")
    if at is not None:
        runtime.clock.advance_to(parse_ts_utc(at))
    trading = _replay_trading(runtime)
    degraded = DegradedState()
    filter_cfg = FilterSettings()
    base = _replay_cycles(
        clock=runtime.clock,
        rng=make_rng(SEED),
        store=runtime.store,
        risk=runtime.risk,
        degraded=degraded,
        dataset_events=list(runtime.dataset.events),
        replay_llm=None,
        dataset_name=runtime.dataset.manifest.dataset,
        filter_cfg=filter_cfg,
        trading=trading,
    )
    bound = build_event_cycles(
        store=runtime.store,
        risk=runtime.risk,
        degraded=degraded,
        trading=trading,
        curves=runtime.curves,
        filter_cfg=filter_cfg,
    )
    seen: list[Seen] = []
    cycles = {seat: _spy(seat, cycle, seen) for seat, cycle in {**base, **bound}.items()}
    supervisor = Supervisor(
        store=runtime.store,
        clock=runtime.clock,
        rng=make_rng(SEED),
        cycles=cycles,
        source="replay",
        degraded=degraded,
        risk=runtime.risk,
        wake_mode="event",
    )
    dlq: list[Event] = []
    bus = EventBus(clock=runtime.clock, handler=supervisor.on_event, dlq=dlq.append)
    await bus.start()
    return Harness(runtime, trading, supervisor, bus, seen, dlq)


async def _close(h: Harness) -> None:
    await h.bus.shutdown()
    h.store.close()


async def _yield(rounds: int = 20) -> None:
    for _ in range(rounds):
        await asyncio.sleep(0)


async def _settle(done: Callable[[], bool]) -> None:
    for _ in range(100_000):
        if done():
            return
        await asyncio.sleep(0)
    raise AssertionError("event delivery did not settle")


async def _publish(
    h: Harness,
    kind: EventKind,
    entity_id: str = MINT_A,
    payload: dict[str, Any] | None = None,
) -> list[Seen]:
    """Publish one event through the bus and return the seat cycles it woke, in run order."""
    start = len(h.seen)
    event = Event(
        kind=kind,
        entity_id=entity_id,
        payload=FrozenPayload(payload if payload is not None else {"n": 1}),
        occurred_at=TICK_A,
    )
    await h.bus.publish(event)
    await _yield()
    if kind is EventKind.mark:
        # Mark is debounced on the clock: let its timer fire.
        h.runtime.clock.advance_to(h.runtime.clock.now() + P2_DEBOUNCE_S)
    want = len(wake_order(kind))
    await _settle(lambda: len(h.seen) - start >= want)
    await _yield()
    return h.seen[start:]


def _result(seen: list[Seen], seat: str) -> dict[str, Any]:
    matches = [result for name, _, result in seen if name == seat]
    assert matches, f"{seat} did not run"
    return matches[-1]


def _rows(h: Harness, *types: str) -> list[dict[str, Any]]:
    return h.store.read(types=list(types), limit=None)


@pytest.mark.parametrize("kind", list(EventKind), ids=lambda kind: kind.value)
async def test_each_event_wakes_its_seats_once_with_that_event(tmp_path: Path, kind: EventKind) -> None:
    h = await _open(tmp_path)
    try:
        before = {seat: h.supervisor.tasks[seat].cycles for seat in ROSTER}
        seen = await _publish(h, kind)
        expected = wake_order(kind)
        assert [seat for seat, _, _ in seen] == list(expected)
        assert {kind_seen for _, kind_seen, _ in seen} == {kind.value}
        for seat in expected:
            assert h.supervisor.tasks[seat].cycles == before[seat] + 1, seat
            assert h.supervisor.tasks[seat].crashes == 0, seat
        assert h.dlq == []
    finally:
        await _close(h)


async def test_each_bound_role_reports_its_own_service_result(tmp_path: Path) -> None:
    h = await _open(tmp_path)
    try:
        chief = _result(await _publish(h, EventKind.position_opened, MINT_A), CHIEF)
        assert isinstance(chief["kill_switch"], bool)
        assert chief["autonomy"] == "manual-ticket"
        assert chief["trigger"] == EventKind.position_opened.value

        scout = _result(await _publish(h, EventKind.token_created, MINT_A), SCOUT)
        assert scout["mint"] == MINT_A
        assert scout["decision"] in {"buy", "skip"}
        assert isinstance(scout["reason"], str)

        risk = _result(await _publish(h, EventKind.curve_tick, MINT_A), RISK)
        assert set(risk) >= {"halt", "trigger"}

        rug = _result(await _publish(h, EventKind.curve_tick, MINT_A), RUG)
        assert rug["verdict"] in {"READABLE", "BLIND", "UNREAD"}

        exit_seat = _result(await _publish(h, EventKind.exit_signal, MINT_A), EXIT)
        assert isinstance(exit_seat["rule_sells"], int)
        assert isinstance(exit_seat["open"], int)
    finally:
        await _close(h)


async def test_intent_places_one_buy_through_risk_and_the_granted_tool(tmp_path: Path) -> None:
    h = await _open(tmp_path)
    try:
        seen = await _publish(h, EventKind.strategy_intent, MINT_A)
        sniper = _result(seen, SNIPER)
        assert sniper == {"orders": 1, "status": "filled", "reason": "ok", "trigger": "strategy_intent"}
        assert [t.mint for t in h.trading.attempts] == [MINT_A]
        assert len(_rows(h, "PositionOpened")) == 1
        assert len(_rows(h, "FillRecorded")) == 1
    finally:
        await _close(h)


async def test_risk_veto_withholds_every_order(tmp_path: Path) -> None:
    h = await _open(tmp_path)
    try:
        seen = await _publish(h, EventKind.risk_veto, MINT_A)
        assert _result(seen, SNIPER) == {"orders": 0, "withheld": "risk_veto", "trigger": "risk_veto"}
        await _publish(h, EventKind.halt, MINT_A)
        assert _result(h.seen, SNIPER)["withheld"] == "halt"
        assert h.trading.attempts == []
        assert _rows(h, "OrderPlaced") == []
        assert _rows(h, "PositionOpened") == []
    finally:
        await _close(h)


async def test_engaged_kill_switch_refuses_the_intent_inside_risk(tmp_path: Path) -> None:
    h = await _open(tmp_path)
    try:
        # The desk's own kill-switch fold: a KillSwitchSet row with no later clear.
        h.store.append(
            ts_utc=TICK_A,
            source="replay",
            correlation_id="desk",
            idempotency_key="test:kill-switch",
            type="KillSwitchSet",
            payload={
                "source": "replay",
                "origin": "test",
                "reason": "test",
                "flatten_requested": False,
                "set_by": "test",
            },
        )
        seen = await _publish(h, EventKind.strategy_intent, MINT_A)
        assert _result(seen, SNIPER)["status"] != "filled"
        assert [t.outcome for t in h.trading.attempts] != ["filled"]
        assert _rows(h, "PositionOpened") == []
        assert _rows(h, "FillRecorded") == []
        assert _result(await _publish(h, EventKind.halt, MINT_A), CHIEF)["kill_switch"] is True
    finally:
        await _close(h)


async def _intent_fill_price(tmp_path: Path, payload: dict[str, Any]) -> str:
    h = await _open(tmp_path)
    try:
        await _publish(h, EventKind.strategy_intent, MINT_A, payload)
        fills = _rows(h, "FillRecorded")
        assert len(fills) == 1
        return str(fills[0]["payload"]["price_avg"])
    finally:
        await _close(h)


async def test_intent_price_comes_from_the_curve_not_the_event(tmp_path: Path) -> None:
    clean = await _intent_fill_price(tmp_path / "clean", {"n": 1})
    bogus = await _intent_fill_price(
        tmp_path / "bogus", {"n": 1, "price_avg": "1", "price": 1, "S": 1, "T": 1}
    )
    assert clean == bogus
    assert Decimal(clean) != 1


async def test_timer_start_runs_risk_and_exit_passes_without_an_event(tmp_path: Path) -> None:
    h = await _open(tmp_path)
    try:
        await h.supervisor.run_once()
        risk = [r for name, kind, r in h.seen if name == RISK]
        exit_runs = [r for name, kind, r in h.seen if name == EXIT]
        assert risk and exit_runs
        assert all(kind is None for name, kind, _ in h.seen if name in (RISK, EXIT))
        assert risk[-1]["trigger"] == "timer"
        assert exit_runs[-1]["trigger"] == "timer"
        assert isinstance(exit_runs[-1]["rule_sells"], int)
    finally:
        await _close(h)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_event_cycles_never_import_the_grok_gateway() -> None:
    modules = _imported_modules(EVENT_CYCLES)
    assert not [name for name in modules if name.startswith("pumpgrok.grok")]


def test_exit_path_loads_without_the_grok_gateway() -> None:
    code = (
        "import sys; import pumpgrok.supervisor.scheduler.event_cycles as m;"
        "print('pumpgrok.grok' in sys.modules)"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, timeout=120
    )
    assert out.stdout.strip() == "False"


async def test_bound_cycles_are_exactly_the_registered_event_seats(tmp_path: Path) -> None:
    h = await _open(tmp_path)
    try:
        bound = build_event_cycles(
            store=h.store,
            risk=h.runtime.risk,
            degraded=DegradedState(),
            trading=h.trading,
            curves=h.runtime.curves,
            filter_cfg=FilterSettings(),
        )
        assert set(bound) == set(EVENT_CYCLE_SEATS)
        assert set(bound) <= {seat for row in SEAT_WAKES.values() for seat in row}
        assert set(bound) < set(ROSTER)
    finally:
        await _close(h)


def test_event_cycles_use_only_the_injected_clock() -> None:
    tree = ast.parse(EVENT_CYCLES.read_text(encoding="utf-8"))
    forbidden = {"time", "asyncio.sleep", "datetime.now", "datetime.utcnow"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {alias.name for alias in node.names} & {"time", "datetime"}
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            assert f"{node.value.id}.{node.attr}" not in forbidden
