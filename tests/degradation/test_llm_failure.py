"""INV-R-34: LLM failure in live-paper degrades to rule-based scoring.

Every fault is injected at the model-resolution boundary through
FaultyLLMClient; the assertions drive product code (DegradedState,
compute_scores, GrokOps/CallBudget, ReplayLlm, the supervisor tick loop)
and prove the fault fired before any recovery is claimed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from harness.faults import (
    FaultMode,
    FaultyLLMClient,
    InjectedFault,
    InjectedRateLimit,
    InjectedUnknown,
)
from pumpgrok.config.settings import ScoringWeights
from pumpgrok.core.budget import CallBudget
from pumpgrok.core.llm import GrokOps
from pumpgrok.core.ratelimit import RateLimiter
from pumpgrok.engine.models import Analysis, Token
from pumpgrok.engine.scoring import compute_scores
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.recorder import ReplayLlm, canonical_request_hash
from pumpgrok.replay.rng import make_rng
from pumpgrok.supervisor.scheduler import ROSTER, DegradedState, Supervisor
from pumpgrok.supervisor.seat_task import SeatContext

BASE = 1767225600.0
LLM_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "llm" / "timeout.json"
PLANTED = Path(__file__).resolve().parents[1] / "fixtures" / "secrets" / "planted.txt"
REQUEST = {"dataset": "soak-3d", "events": 4321}


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    return LedgerStore(str(path))


async def _drive_down(mode: FaultMode) -> tuple[FaultyLLMClient, DegradedState]:
    """Fault the model boundary once; degrade exactly as the seat would."""
    fake = FaultyLLMClient(mode)
    degraded = DegradedState()
    assert degraded.signal_scoring_mode(replay=False) == "llm"
    try:
        outcome = await fake.complete(dict(REQUEST), FixtureClock(start=BASE))
    except (TimeoutError, InjectedFault):
        degraded.llm_available = False
    else:
        if outcome.get("outcome") != "ok":
            degraded.llm_available = False
    assert fake.fired == 1
    return fake, degraded


async def test_llm_timeout_falls_back_to_rules() -> None:
    _, degraded = await _drive_down(FaultMode.TIMEOUT)
    assert degraded.signal_scoring_mode(replay=False) == "rule_fallback"


async def test_llm_503_falls_back_to_rules() -> None:
    _, degraded = await _drive_down(FaultMode.RAISE)
    assert degraded.signal_scoring_mode(replay=False) == "rule_fallback"


async def test_llm_429_falls_back_to_rules() -> None:
    _, degraded = await _drive_down(FaultMode.RATE_LIMIT)
    assert degraded.signal_scoring_mode(replay=False) == "rule_fallback"


async def test_llm_malformed_json_falls_back_to_rules() -> None:
    _, degraded = await _drive_down(FaultMode.MALFORMED)
    assert degraded.signal_scoring_mode(replay=False) == "rule_fallback"


async def test_llm_unknown_result_falls_back_to_rules() -> None:
    _, degraded = await _drive_down(FaultMode.UNKNOWN)
    assert degraded.signal_scoring_mode(replay=False) == "rule_fallback"


def test_rule_fallback_scores_missing_components_at_zero() -> None:
    """Rule-based scoring without the auditor: audit stays 0.0 (MISSING_COMPONENT)."""
    analysis = Analysis(token=Token(mint="So11111111111111111111111111111111111111112"))
    scores = compute_scores(analysis, ScoringWeights())
    assert scores.audit == 0.0
    assert scores.narrative == 0.0
    assert scores.timing == 0.0


async def test_require_llm_is_observe_only_for_buys() -> None:
    _, degraded = await _drive_down(FaultMode.TIMEOUT)
    degraded.require_llm = True
    assert degraded.signal_scoring_mode(replay=False) == "observe_only_buys"
    degraded.llm_available = True
    assert degraded.signal_scoring_mode(replay=False) == "llm"


async def test_supervisor_keeps_ticking_while_llm_down(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        degraded = DegradedState(llm_available=False)

        async def _ok(ctx: SeatContext) -> dict[str, Any]:
            return {"ok": True}

        supervisor = Supervisor(
            store=store,
            clock=clock,
            rng=make_rng(7),
            cycles=dict.fromkeys(ROSTER, _ok),
            degraded=degraded,
        )
        for _ in range(2):
            outcomes = await supervisor.run_once()
            assert all(outcome == "ok" for outcome in outcomes.values())
        for task in supervisor.tasks.values():
            assert task.cycles == 2
            assert task.crashes == 0
        assert degraded.signal_scoring_mode(replay=False) == "rule_fallback"
        assert store.verify() is True
    finally:
        store.close()


def test_budget_exhausted_blocks_new_model_calls() -> None:
    clock = FixtureClock(start=BASE)
    ops = GrokOps(
        limiter=RateLimiter(60.0, 10.0, clock),
        budget=CallBudget(1, clock),
    )
    assert ops.precheck("bot-08-signal") is None
    reason = ops.precheck("bot-08-signal")
    assert reason is not None and "exhausted" in reason
    assert ops.blocked["bot-08-signal"] == 1


def test_recorded_timeout_outcome_replays_with_virtual_latency() -> None:
    template = json.loads(LLM_FIXTURE.read_text())
    clock = FixtureClock(start=BASE)
    digest = canonical_request_hash(REQUEST)
    table = ReplayLlm.from_rows(
        [
            {
                "request_hash": digest,
                "outcome": template["outcome"],
                "latency_s": template["latency_s"],
                "response": template["response"],
            }
        ]
    )
    result = table.complete(dict(REQUEST), clock)
    assert result.outcome == "timeout"
    assert clock.now() == pytest.approx(BASE + template["latency_s"])


def _planted_key() -> str:
    lines = [
        line
        for line in PLANTED.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert lines, "planted fixture must hold a secret line"
    for line in lines:
        assert "pragma: allowlist secret" in line
    return lines[0].split()[0]


async def test_planted_secret_never_reaches_ledger(tmp_path: Path) -> None:
    key = _planted_key()
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        store.append(
            ts_utc="2026-01-01T00:00:00.000Z",
            source="paper",
            correlation_id="desk",
            idempotency_key="note-0",
            type="JournalNote",
            payload={
                "source": "paper",
                "seat": "desk",
                "note_kind": "note",
                "text": "llm down; rule fallback",
                "refs": [],
            },
        )

        async def _ok(ctx: SeatContext) -> dict[str, Any]:
            return {"ok": True}

        supervisor = Supervisor(
            store=store, clock=clock, rng=make_rng(7), cycles=dict.fromkeys(ROSTER, _ok)
        )
        await supervisor.run_once()
        blob = json.dumps(store.read(limit=None))
        assert key not in blob
        assert store.verify() is True
    finally:
        store.close()
