"""Event-mode replay goldens: the full ten-seat desk driven through the real EventBus (14-04 B).

Each dataset run opens the replay sandbox, merges the replay bodies with the slice A and slice B
event bodies, and publishes through ``EventBus``:

- each new mint is announced once as ``token_created``;
- each reserve-carrying fixture tick is published as ``curve_tick``;
- each candidate the engine admitted (decision ``buy``) is published as ``strategy_intent`` at its
  tick time, the same candidate stream the replay sniper places from.

After every publish, and after every tick, the supervisor runs the timer seats due at that
instant. A golden pins two hashes of that run:

- ``ledger``: the ledger ``events.hash`` (seeded grants, orders, fills, positions, rollovers);
- ``trace``: sha256 over one JSON line per seat cycle, ``[seat, trigger, result]``, in run order.
  Journal report paths are reduced to their file name, so the trace does not depend on the
  scratch directory.

The trace is what pins the seats that write nothing to the ledger (whale, signal, journal, rug,
chief). smoke-10m admits no candidate, so its ledger is the seeded grants and rollover only.

Only a probe run may set a pin. Probe command (repository root, offline, injected clock):

    .venv/bin/python -c "import sys, asyncio, pathlib, tempfile; sys.path.insert(0, 'tests/desk'); \
import test_event_golden_hashes as g; \
[print(n, asyncio.run(g.run_event_fixture(g.FIXTURES / n, pathlib.Path(tempfile.mkdtemp())))) \
for n in ('smoke-10m', 'smoke')]"

Probe output (two independent runs per fixture, each in a fresh scratch directory; both runs
agreed, and the values above were copied from this output):

    smoke-10m first  ledger=1b28f985c8cef3eec296890821d07475ad8ab917e6c8fa8a2dcbabf610ccf9e4 trace=2effbd39926857b7a30612b21d98c5cc1a3717d0cab64b44743e44b615b619e9 rows=145 intents=0 errors=[] dlq=0
    smoke-10m second ledger=1b28f985c8cef3eec296890821d07475ad8ab917e6c8fa8a2dcbabf610ccf9e4 trace=2effbd39926857b7a30612b21d98c5cc1a3717d0cab64b44743e44b615b619e9 rows=145 intents=0 errors=[] dlq=0
    smoke first      ledger=f6a8a6fa99dde55e304fb7caf4d3f696fb400c01f110cd16652fd8dedfef7747 trace=328c8f93a63014a545016bd6bb4fc1e972393610c0a6bdbf6afdeb6a86ba5aa8 rows=154 intents=2 errors=[] dlq=0
    smoke second     ledger=f6a8a6fa99dde55e304fb7caf4d3f696fb400c01f110cd16652fd8dedfef7747 trace=328c8f93a63014a545016bd6bb4fc1e972393610c0a6bdbf6afdeb6a86ba5aa8 rows=154 intents=2 errors=[] dlq=0

The legacy cadence pins are not touched here: smoke-10m events.hash 1dffa784... (seeded head pin)
and the trading smoke pin 106495a9... stay in their own tests.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.config.settings import FilterSettings
from pumpgrok.events.bus import EventBus
from pumpgrok.events.models import Event, EventKind, FrozenPayload
from pumpgrok.replay.fixtures import event_epoch
from pumpgrok.replay.recorder import load_llm_records
from pumpgrok.replay.rng import make_rng
from pumpgrok.replay.runner import ledger_events_hash
from pumpgrok.supervisor.scheduler import ROSTER, Supervisor, open_replay_runtime
from pumpgrok.supervisor.scheduler.degraded import DegradedState
from pumpgrok.supervisor.scheduler.event_cycles import build_event_cycles, merge_event_cycles
from pumpgrok.supervisor.scheduler.event_cycles_aux import build_aux_event_cycles
from pumpgrok.supervisor.scheduler.orders import _replay_trading
from pumpgrok.supervisor.scheduler.replay_cycles import _replay_cycles
from pumpgrok.supervisor.scheduler.replay_runtime import ReplayRuntime
from pumpgrok.supervisor.scheduler.supervisor import TRIGGER_EVENT
from pumpgrok.supervisor.scheduler.wake import wake_order

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "replay"
SEED = 20260101
SNIPER = "bot-04-sniper"
SHILL = "bot-07-shill"
WHALE = "bot-03-whale"
SIGNAL = "bot-08-signal"
JOURNAL = "bot-09-journal"

#: Pinned (ledger events.hash, seat trace hash) per fixture. Set only from a probe run.
GOLDEN_RUNS: dict[str, tuple[str, str]] = {
    "smoke-10m": (
        "1b28f985c8cef3eec296890821d07475ad8ab917e6c8fa8a2dcbabf610ccf9e4",
        "2effbd39926857b7a30612b21d98c5cc1a3717d0cab64b44743e44b615b619e9",
    ),
    "smoke": (
        "f6a8a6fa99dde55e304fb7caf4d3f696fb400c01f110cd16652fd8dedfef7747",
        "328c8f93a63014a545016bd6bb4fc1e972393610c0a6bdbf6afdeb6a86ba5aa8",
    ),
}


@dataclass
class EventRun:
    dataset: str
    ledger_hash: str
    trace_hash: str
    rows: int
    dispatch: Counter[tuple[str, str]] = field(default_factory=Counter)
    errors: list[str] = field(default_factory=list)
    dlq: int = 0
    intents: int = 0


Seen = tuple[str, str | None, dict[str, Any]]


def _normal(result: Mapping[str, Any]) -> dict[str, Any]:
    """A result with scratch-directory paths reduced to file names (deterministic trace)."""
    out = dict(result)
    if isinstance(out.get("rollup"), str):
        out["rollup"] = Path(out["rollup"]).name
    return out


def _spy(
    seat: str, cycle: Callable[[Any], Any], seen: list[Seen], errors: list[str]
) -> Callable[[Any], Any]:
    async def _run(ctx: Any) -> Any:
        trigger = TRIGGER_EVENT.get()
        kind = None if trigger is None else trigger.kind.value
        try:
            result = await cycle(ctx)
        except BaseException as exc:
            errors.append(f"{seat}:{kind}:{exc!r}")
            seen.append((seat, kind, {"error": repr(exc)}))
            raise
        seen.append((seat, kind, _normal(result or {})))
        return result

    return _run


def _trace_hash(seen: list[Seen]) -> str:
    digest = hashlib.sha256()
    for seat, kind, result in seen:
        line = json.dumps([seat, kind, result], sort_keys=True, default=str)
        digest.update(line.encode("utf-8") + b"\n")
    return digest.hexdigest()


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
    bus: EventBus,
    seen: list[Seen],
    kind: EventKind,
    mint: str,
    payload: dict[str, Any],
    occurred_at: str,
) -> None:
    before = len(seen)
    event = Event(
        kind=kind,
        entity_id=mint,
        payload=FrozenPayload(payload),
        occurred_at=occurred_at,
    )
    await bus.publish(event)
    await _yield()
    await _settle(lambda: len(seen) - before >= len(wake_order(kind)))
    await _yield()


def _token_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    name = row.get("name")
    return {"name": name} if isinstance(name, str) else {}


def _tick_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {"S": int(row["S"]), "T": int(row["T"]), "complete": bool(row.get("complete", False))}


async def run_event_fixture(dataset_dir: Path, scratch: Path) -> EventRun:
    """One deterministic event-mode run of a fixture dataset through the bus."""
    scratch.mkdir(parents=True, exist_ok=True)
    runtime: ReplayRuntime = open_replay_runtime(
        dataset_dir, FilterSettings(), seed=SEED, ledger_path=scratch / "ledger.sqlite"
    )
    trading = _replay_trading(runtime)
    degraded = DegradedState()
    filter_cfg = FilterSettings()
    dataset_name = runtime.dataset.manifest.dataset
    events = list(runtime.dataset.events)
    replay_llm = load_llm_records(dataset_dir)
    base = _replay_cycles(
        clock=runtime.clock,
        rng=make_rng(SEED),
        store=runtime.store,
        risk=runtime.risk,
        degraded=degraded,
        dataset_events=events,
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
        rpc=None,
        replay_llm=replay_llm,
        dataset_name=dataset_name,
        dataset_events=events,
        trading=trading,
        journal_dir=scratch / "journal",
        reports_dir=scratch / "reports",
    )
    seen: list[Seen] = []
    errors: list[str] = []
    merged = merge_event_cycles(base, six, aux)
    assert set(merged) == set(ROSTER)
    cycles = {seat: _spy(seat, cycle, seen, errors) for seat, cycle in merged.items()}
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
    buys: dict[float, list[str]] = {}
    for candidate in runtime.candidates:
        if candidate.verdict.decision == "buy":
            buys.setdefault(candidate.ts, []).append(candidate.verdict.mint)
    intents = 0
    try:
        admitted: set[str] = set()
        for row in events:
            stamp = event_epoch(row)
            if stamp > runtime.clock.now():
                runtime.clock.advance_to(stamp)
            mint = str(row["mint"])
            when = str(row["ts_utc"])
            if mint not in admitted:
                admitted.add(mint)
                await _publish(bus, seen, EventKind.token_created, mint, _token_payload(row), when)
            if "S" in row and "T" in row:
                await _publish(bus, seen, EventKind.curve_tick, mint, _tick_payload(row), when)
            for buy_mint in buys.get(stamp, []):
                intents += 1
                await _publish(
                    bus, seen, EventKind.strategy_intent, buy_mint, {"decision": "buy"}, when
                )
            await supervisor.tick_once()
        rows = len(runtime.store.read(limit=None))
    finally:
        await bus.shutdown()
        runtime.store.close()
    dispatch: Counter[tuple[str, str]] = Counter()
    for seat, kind, _ in seen:
        dispatch[(seat, kind or "timer")] += 1
    return EventRun(
        dataset=dataset_name,
        ledger_hash=ledger_events_hash(runtime.ledger_path),
        trace_hash=_trace_hash(seen),
        rows=rows,
        dispatch=dispatch,
        errors=errors,
        dlq=len(dlq),
        intents=intents,
    )


@pytest.fixture(scope="module")
def smoke_10m(tmp_path_factory: pytest.TempPathFactory) -> EventRun:
    scratch = tmp_path_factory.mktemp("event-smoke-10m")
    return asyncio.run(run_event_fixture(FIXTURES / "smoke-10m", scratch))


@pytest.fixture(scope="module")
def smoke(tmp_path_factory: pytest.TempPathFactory) -> EventRun:
    scratch = tmp_path_factory.mktemp("event-smoke")
    return asyncio.run(run_event_fixture(FIXTURES / "smoke", scratch))


def _by_name(name: str, smoke_10m: EventRun, smoke: EventRun) -> EventRun:
    return smoke_10m if name == "smoke-10m" else smoke


@pytest.mark.parametrize("name", ["smoke-10m", "smoke"])
def test_event_run_matches_its_pinned_golden(
    name: str, smoke_10m: EventRun, smoke: EventRun
) -> None:
    run = _by_name(name, smoke_10m, smoke)
    assert name in GOLDEN_RUNS, f"no pinned golden for {name}"
    ledger, trace = GOLDEN_RUNS[name]
    assert run.ledger_hash == ledger
    assert run.trace_hash == trace


@pytest.mark.parametrize("name", ["smoke-10m", "smoke"])
def test_event_run_has_no_errors_and_no_dead_letters(
    name: str, smoke_10m: EventRun, smoke: EventRun
) -> None:
    run = _by_name(name, smoke_10m, smoke)
    assert run.errors == []
    assert run.dlq == 0


def test_shill_never_runs_in_the_event_runs(smoke_10m: EventRun, smoke: EventRun) -> None:
    for run in (smoke_10m, smoke):
        assert not [key for key in run.dispatch if key[0] == SHILL]


def test_smoke_intents_run_the_sniper_once_per_admitted_candidate(smoke: EventRun) -> None:
    assert smoke.intents == 2
    assert smoke.dispatch[(SNIPER, EventKind.strategy_intent.value)] == 2


def test_smoke_10m_admits_no_candidate_so_no_intent_reaches_the_sniper(
    smoke_10m: EventRun,
) -> None:
    assert smoke_10m.intents == 0
    assert smoke_10m.dispatch[(SNIPER, EventKind.strategy_intent.value)] == 0


def test_whale_and_signal_run_on_each_new_mint_and_never_on_ticks(smoke_10m: EventRun) -> None:
    created = smoke_10m.dispatch[(WHALE, EventKind.token_created.value)]
    assert created >= 1
    assert smoke_10m.dispatch[(SIGNAL, EventKind.token_created.value)] == created
    assert smoke_10m.dispatch[(WHALE, EventKind.curve_tick.value)] == 0
    assert smoke_10m.dispatch[(SIGNAL, EventKind.curve_tick.value)] == 0


def test_journal_runs_only_on_its_timer_in_the_event_runs(smoke_10m: EventRun, smoke: EventRun) -> None:
    for run in (smoke_10m, smoke):
        assert run.dispatch[(JOURNAL, EventKind.curve_tick.value)] == 0
        assert run.dispatch[(JOURNAL, EventKind.token_created.value)] == 0
        assert run.dispatch[(JOURNAL, "timer")] >= 1


def test_event_mode_run_is_deterministic(tmp_path: Path) -> None:
    first = asyncio.run(run_event_fixture(FIXTURES / "smoke", tmp_path / "a"))
    second = asyncio.run(run_event_fixture(FIXTURES / "smoke", tmp_path / "b"))
    assert first.ledger_hash == second.ledger_hash
    assert first.trace_hash == second.trace_hash
    assert first.rows == second.rows
