"""Auxiliary seat cycles bound to bus events: whale, signal and journal (EVT-10, 14-04 slice B).

Every event goes through the real EventBus into the supervisor's event dispatch. The seats
recorded for each event are compared with the owner-confirmed wake matrix. Shill has no row in
that matrix, so no event may ever run it. The signal body reads recorded model outcomes from the
smoke-10m fixture; the whale body reports BLIND without an RPC endpoint and never invents
transfers; the journal body writes its own notes through ``journal.append``.
"""

from __future__ import annotations

import ast
import asyncio
import subprocess
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.config.settings import FilterSettings
from pumpgrok.events.bus import EventBus
from pumpgrok.events.constants import P2_DEBOUNCE_S
from pumpgrok.events.models import Event, EventKind, FrozenPayload
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import parse_ts_utc
from pumpgrok.replay.recorder import canonical_request_hash, load_llm_records
from pumpgrok.replay.rng import make_rng
from pumpgrok.replay.runner import llm_request_for
from pumpgrok.supervisor.scheduler import ROSTER, Supervisor, open_replay_runtime
from pumpgrok.supervisor.scheduler.degraded import DegradedState
from pumpgrok.supervisor.scheduler.event_cycles import build_event_cycles, merge_event_cycles
from pumpgrok.supervisor.scheduler.event_cycles_aux import build_aux_event_cycles
from pumpgrok.supervisor.scheduler.orders import _replay_trading
from pumpgrok.supervisor.scheduler.replay_cycles import _replay_cycles
from pumpgrok.supervisor.scheduler.replay_runtime import ReplayRuntime, _ReplayTrading
from pumpgrok.supervisor.scheduler.supervisor import TRIGGER_EVENT
from pumpgrok.supervisor.scheduler.wake import (
    AUX_EVENT_CYCLE_SEATS,
    EVENT_CYCLE_SEATS,
    SEAT_WAKES,
    wake_order,
)
from pumpgrok.tools.onchain.rpc import RpcError

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "tests" / "fixtures" / "replay" / "smoke"
SMOKE_10M = REPO / "tests" / "fixtures" / "replay" / "smoke-10m"
EVENT_AUX = REPO / "src" / "pumpgrok" / "supervisor" / "scheduler" / "event_cycles_aux.py"
SEED = 20260101
#: Pre-graduation mint with a curve read at 00:00:01.250Z (fixture S = 42.35e9 lamports).
MINT_A = "SmokeMintAAAA1111111111111111111111111111111"
TICK_A = "2026-01-01T00:00:01.250Z"

CHIEF = "bot-00-chief"
SCOUT = "bot-01-scout"
RISK = "bot-02-risk"
WHALE = "bot-03-whale"
SNIPER = "bot-04-sniper"
RUG = "bot-05-rug"
EXIT = "bot-06-exit"
SHILL = "bot-07-shill"
SIGNAL = "bot-08-signal"
JOURNAL = "bot-09-journal"
AUX = (WHALE, SIGNAL, JOURNAL)

#: Event kinds that wake at least one auxiliary seat.
AUX_KINDS = tuple(kind for kind in EventKind if set(SEAT_WAKES[kind]) & set(AUX))

Seen = tuple[str, str | None, dict[str, Any]]


class _FakeRpc:
    """Offline RPC double: records every call and fails the supply read (no network)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[Any]]] = []

    async def call(self, method: str, params: list[Any]) -> Any:
        self.calls.append((method, params))
        raise RpcError(f"offline fake: {method}")


@dataclass
class Harness:
    runtime: ReplayRuntime
    trading: _ReplayTrading
    supervisor: Supervisor
    bus: EventBus
    degraded: DegradedState
    journal_dir: Path
    reports_dir: Path
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


async def _open(
    tmp_path: Path,
    *,
    dataset: Path = SMOKE,
    rpc: Any | None = None,
    degraded: DegradedState | None = None,
) -> Harness:
    runtime = open_replay_runtime(dataset, FilterSettings(), seed=SEED, ledger_path=tmp_path / "l.db")
    runtime.clock.advance_to(parse_ts_utc(TICK_A))
    trading = _replay_trading(runtime)
    degraded = degraded if degraded is not None else DegradedState()
    filter_cfg = FilterSettings()
    dataset_name = runtime.dataset.manifest.dataset
    replay_llm = load_llm_records(dataset)
    journal_dir = tmp_path / "journal"
    reports_dir = tmp_path / "reports"
    base = _replay_cycles(
        clock=runtime.clock,
        rng=make_rng(SEED),
        store=runtime.store,
        risk=runtime.risk,
        degraded=degraded,
        dataset_events=list(runtime.dataset.events),
        replay_llm=replay_llm,
        dataset_name=dataset_name,
        filter_cfg=filter_cfg,
        trading=trading,
    )
    six = build_event_cycles(
        store=runtime.store,
        risk=runtime.risk,
        degraded=degraded,
        trading=trading,
        curves=runtime.curves,
        filter_cfg=filter_cfg,
    )
    aux = build_aux_event_cycles(
        store=runtime.store,
        degraded=degraded,
        rpc=rpc,
        replay_llm=replay_llm,
        dataset_name=dataset_name,
        dataset_events=list(runtime.dataset.events),
        trading=trading,
        journal_dir=journal_dir,
        reports_dir=reports_dir,
    )
    seen: list[Seen] = []
    merged = merge_event_cycles(base, six, aux)
    cycles = {seat: _spy(seat, cycle, seen) for seat, cycle in merged.items()}
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
    return Harness(runtime, trading, supervisor, bus, degraded, journal_dir, reports_dir, seen, dlq)


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
    occurred_at: str = TICK_A,
) -> list[Seen]:
    """Publish one event through the bus and return the seat cycles it woke, in run order."""
    start = len(h.seen)
    event = Event(
        kind=kind,
        entity_id=entity_id,
        payload=FrozenPayload(payload if payload is not None else {"n": 1}),
        occurred_at=occurred_at,
    )
    await h.bus.publish(event)
    await _yield()
    if kind is EventKind.mark:
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


@pytest.mark.parametrize("kind", AUX_KINDS, ids=lambda kind: kind.value)
async def test_each_aux_event_wakes_exactly_its_matrix_seats_in_roster_order(
    tmp_path: Path, kind: EventKind
) -> None:
    h = await _open(tmp_path)
    try:
        seen = await _publish(h, kind)
        assert [seat for seat, _, _ in seen] == list(wake_order(kind))
        assert all(trigger == kind.value for _, trigger, _ in seen)
        assert h.dlq == []
    finally:
        await _close(h)


async def test_shill_is_never_run_by_any_event(tmp_path: Path) -> None:
    h = await _open(tmp_path)
    try:
        for kind in EventKind:
            seen = await _publish(h, kind)
            assert SHILL not in [seat for seat, _, _ in seen], kind
        assert SHILL not in AUX_EVENT_CYCLE_SEATS
        assert SHILL not in EVENT_CYCLE_SEATS
        assert h.dlq == []
    finally:
        await _close(h)


@pytest.mark.parametrize("kind", [EventKind.kill_switch, EventKind.halt], ids=lambda k: k.value)
async def test_signal_stands_down_on_kill_switch_and_halt(tmp_path: Path, kind: EventKind) -> None:
    h = await _open(tmp_path, dataset=SMOKE_10M)
    try:
        seen = await _publish(h, kind)
        assert _result(seen, SIGNAL) == {
            "scoring": "withheld",
            "withheld": kind.value,
            "trigger": kind.value,
        }
    finally:
        await _close(h)


async def test_signal_scores_a_candidate_from_its_recorded_outcome(tmp_path: Path) -> None:
    h = await _open(tmp_path, dataset=SMOKE_10M)
    try:
        first = h.runtime.dataset.events[0]
        mint = str(first["mint"])
        request = llm_request_for(
            h.runtime.dataset.manifest.dataset, list(h.runtime.dataset.events)
        )
        recorded = load_llm_records(SMOKE_10M)
        assert recorded is not None
        expected = recorded.lookup(canonical_request_hash(request)).outcome
        clock_before = h.runtime.clock.now()
        seen = await _publish(h, EventKind.token_created, entity_id=mint)
        result = _result(seen, SIGNAL)
        assert result["scoring"] == "llm"
        assert result["outcome"] == expected
        assert result["trigger"] == EventKind.token_created.value
        assert h.runtime.clock.now() == clock_before
    finally:
        await _close(h)


async def test_signal_without_recorded_model_outcomes_is_skipped_not_invented(
    tmp_path: Path,
) -> None:
    h = await _open(tmp_path)
    try:
        seen = await _publish(h, EventKind.token_created)
        assert _result(seen, SIGNAL) == {
            "scoring": "skipped",
            "reason": "no_model_records",
            "trigger": EventKind.token_created.value,
        }
    finally:
        await _close(h)


async def test_whale_reports_blind_without_rpc_and_invents_no_transfers(tmp_path: Path) -> None:
    h = await _open(tmp_path)
    try:
        seen = await _publish(h, EventKind.token_created)
        assert _result(seen, WHALE) == {
            "verdict": "BLIND",
            "reason": "no_rpc",
            "mint": MINT_A,
            "trigger": EventKind.token_created.value,
        }
    finally:
        await _close(h)


async def test_whale_reports_blind_when_every_rpc_endpoint_is_down(tmp_path: Path) -> None:
    rpc = _FakeRpc()
    degraded = DegradedState(rpc_endpoints=[False])
    h = await _open(tmp_path, rpc=rpc, degraded=degraded)
    try:
        seen = await _publish(h, EventKind.migration)
        assert _result(seen, WHALE)["verdict"] == "BLIND"
        assert rpc.calls == []
    finally:
        await _close(h)


async def test_whale_watches_the_event_mint_over_rpc_and_reports_unread(tmp_path: Path) -> None:
    rpc = _FakeRpc()
    h = await _open(tmp_path, rpc=rpc)
    try:
        seen = await _publish(h, EventKind.token_created)
        assert rpc.calls[0] == ("getTokenSupply", [MINT_A])
        result = _result(seen, WHALE)
        assert result["verdict"] == "UNREAD"
        assert result["mint"] == MINT_A
        assert "error" not in result
    finally:
        await _close(h)


async def test_trade_writes_a_journal_note_bound_to_the_journal_seat(tmp_path: Path) -> None:
    h = await _open(tmp_path)
    try:
        seen = await _publish(h, EventKind.trade)
        result = _result(seen, JOURNAL)
        assert result["noted"] is True
        rows = _rows(h, "JournalNote")
        assert len(rows) == 1
        payload = rows[0]["payload"]
        assert payload["seat"] == JOURNAL
        assert payload["note_kind"] == "note"
        assert payload["source"] == "paper"
        assert (h.journal_dir).is_dir()
        assert list(h.journal_dir.glob("*.jsonl")), "journal export was not written"
    finally:
        await _close(h)


async def test_journal_repeat_of_the_same_event_is_not_noted_twice(tmp_path: Path) -> None:
    h = await _open(tmp_path)
    try:
        await _publish(h, EventKind.position_opened)
        await _publish(h, EventKind.position_opened, occurred_at="2026-01-01T00:00:02.000Z")
        assert len(_rows(h, "JournalNote")) == 1
    finally:
        await _close(h)


def test_aux_cycles_never_import_the_grok_gateway() -> None:
    tree = ast.parse(EVENT_AUX.read_text(encoding="utf-8"))
    names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not [name for name in names if name.startswith("pumpgrok.grok")]


def test_aux_cycles_use_only_the_injected_clock() -> None:
    tree = ast.parse(EVENT_AUX.read_text(encoding="utf-8"))
    forbidden = {"time.time", "time.monotonic", "asyncio.sleep", "datetime.now"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            value = node.func.value
            if isinstance(value, ast.Name):
                assert f"{value.id}.{node.func.attr}" not in forbidden


def test_aux_cycles_import_the_grok_free_bodies_without_grok() -> None:
    code = (
        "import sys\n"
        "import pumpgrok.supervisor.scheduler.event_cycles_aux\n"
        "print('pumpgrok.grok' in sys.modules)\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, timeout=120
    )
    assert out.stdout.strip() == "False"


def test_merge_keeps_replay_bodies_for_seats_outside_the_event_sets() -> None:
    async def _replay(ctx: Any) -> dict[str, Any]:
        return {"replay": True}

    async def _bound(ctx: Any) -> dict[str, Any]:
        return {"bound": True}

    replay = dict.fromkeys(ROSTER, _replay)
    merged = merge_event_cycles(replay, {WHALE: _bound, SIGNAL: _bound, JOURNAL: _bound})
    assert set(merged) == set(ROSTER)
    assert merged[SHILL] is _replay
    assert merged[WHALE] is _bound


def test_merge_refuses_a_bound_body_for_a_seat_no_event_wakes() -> None:
    async def _bound(ctx: Any) -> dict[str, Any]:
        return {}

    with pytest.raises(ValueError, match="bot-07-shill"):
        merge_event_cycles({}, {SHILL: _bound})


def test_aux_seats_are_exactly_the_event_bodies_this_slice_adds() -> None:
    assert frozenset(AUX) == AUX_EVENT_CYCLE_SEATS
    assert set(AUX) & EVENT_CYCLE_SEATS == set()
