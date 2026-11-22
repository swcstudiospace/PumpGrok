"""RT-03/PRM-05: the event desk runs end to end on recorded data.

Feed events enter the bus, an evidence edge promotes a strategy one
stage, and the gateway budget is a real LayeredBudget that the e2e
exhausts (one strategy fills its budget and is refused). The recorded
ledger digest matches a golden value captured on first run.
"""

from __future__ import annotations

import asyncio
import hashlib
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.core.adapter import ExecutionMode
from pumpgrok.events.models import Event
from pumpgrok.grok import BudgetExhausted, GatewayRequest, LayeredBudget
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.promotion.evaluator import EvidenceView
from pumpgrok.promotion.stages import Stage, read_stage_row
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.supervisor.event_desk import build_event_desk

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
STRATEGY = "momentum_breakout"


def _golden_digest(store: LedgerStore) -> str:
    digest = hashlib.sha256()
    for event in store.read(limit=None):
        digest.update(str(event["hash"]).encode())
    return digest.hexdigest()


def _evidence() -> EvidenceView:
    return EvidenceView(
        strategy_id=STRATEGY,
        eligible=True,
        paper_days=14,
        closed_trades=50,
        profit_factor=Decimal("1.25"),
        drawdown_fraction=Decimal("0.10"),
        param_hash="a" * 64,
        version_id="v1",
        evidence_run_id="RUN-1",
        event_id="evt-1",
    )


def test_event_desk_e2e_promotes_and_exhausts_real_budget(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", "10000000000")
    store.set_meta("source", "paper")
    desk = build_event_desk(
        mode=ExecutionMode.PAPER,
        store=store,
        clock=clock,
        place=lambda intent: None,
        params={"momentum_breakout": {"breakout_bps": 100}},
        sidecar_path=tmp_path / "sidecar.sqlite",
        budget=LayeredBudget(window_cap=10, agent_cap=2, global_cap=10),
    )
    # Evidence edge: one strategy moves exactly one stage.
    row = desk.handle_evidence(_evidence())
    assert row.stage is Stage.PAPER
    assert read_stage_row(store, STRATEGY).stage is Stage.PAPER  # type: ignore[union-attr]

    # Feed event enters the bus; the evaluator subscription is wired.
    async def _drive() -> None:
        await desk.bus.start()
        await desk.bus.publish(
            Event(
                kind="strategy_intent",
                entity_id=STRATEGY,
                payload={"evidence": {"strategy_id": STRATEGY, "eligible": True, "paper_days": 14, "closed_trades": 50, "profit_factor": "1.25", "drawdown_fraction": "0.10", "param_hash": "a"*64, "version_id": "v1", "evidence_run_id": "RUN-1", "event_id": "evt-9"}},
                occurred_at=format_ts_utc(clock.now()),
            )
        )
        await desk.bus.shutdown()

    asyncio.run(_drive())

    # The real LayeredBudget exhausts: the third call is refused.
    async def _spend() -> None:
        for index in range(2):
            await desk.gateway.call(
                GatewayRequest(
                    agent=STRATEGY,
                    prompt=f"e2e-{index}",
                    consequence_id=f"e2e-{index}",
                    score=100,
                    model="replay",
                    cost=1,
                )
            )

    asyncio.run(_spend())
    with pytest.raises(BudgetExhausted):
        asyncio.run(
            desk.gateway.call(
                GatewayRequest(
                    agent=STRATEGY,
                    prompt="e2e-2",
                    consequence_id="e2e-2",
                    score=100,
                    model="replay",
                    cost=1,
                )
            )
        )

    # Golden digest over the recorded ledger chain, captured on first run.
    golden = _golden_digest(store)
    assert len(golden) == 64
    digest_path = Path(__file__).with_name("golden_event_desk_digest.txt")
    if not digest_path.exists():
        digest_path.write_text(golden, encoding="utf-8")
    assert digest_path.read_text(encoding="utf-8").strip() == golden
