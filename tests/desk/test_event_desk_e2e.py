"""RT-03 / criterion 10: recorded events run through the event desk, end to end.

Offline. Recorded candidates go through the bus into the Grok gateway over a real LayeredBudget,
which the test exhausts. A recorded tick goes through the strategy runtime into the intent
router. A ledger row of a trigger type reaches the promotion evaluator. The transports and the
evidence sources are recording doubles; no network is reached. Nothing here is skipped.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar

import pytest

from datafeed.readonly_double import ReadOnlyDouble
from pumpgrok.config.settings import Settings
from pumpgrok.events.event_desk import EventDesk, build_event_desk
from pumpgrok.events.models import Event, EventKind
from pumpgrok.grok.gateway import GrokRequest
from pumpgrok.ledger.events import PositionClosed, PositionOpened
from pumpgrok.ledger.ticket_refs import append_with_ticket_ref
from pumpgrok.promotion.evaluator import EvidenceSource, PromotionEvidence
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.risk.entry_checks import EntryEvidence
from pumpgrok.strategies.base import Intent, Strategy, StrategyContext, TickSnapshot

START = 1_700_000_000.0
STRATEGY = "scripted_buy"
DECISION = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
TICKET = "SOL-20260101-001"
SIZE = 400_000
CANDIDATE_MINTS = tuple(f"MintDeskCandidate{index}" for index in range(5))
POSITION_MINT = "MintDeskPosition"
_SETTLE_ROUNDS = 1_000


class RecordingGrok:
    """GrokTransport double: answers every call and keeps the text it was asked."""

    def __init__(self) -> None:
        self.texts: list[str] = []

    async def __call__(self, request: GrokRequest, text: str) -> str:
        self.texts.append(text)
        return "admit"


class ScriptedStrategy:
    """Strategy double: one buy Intent for every tick it sees."""

    strategy_id: ClassVar[str] = STRATEGY
    BOUNDS: ClassVar[Mapping[str, Any]] = {}
    DEFAULTS: ClassVar[Mapping[str, Any]] = {}

    def on_tick(self, context: StrategyContext) -> tuple[Intent, ...]:
        return (
            Intent(
                strategy_id=STRATEGY,
                mint=context.tick.mint,
                side="buy",
                size_lamports=SIZE,
                decision_id=DECISION,
                reason="scripted",
                version_id=context.version_id,
            ),
        )


def _settings() -> Settings:
    return Settings(mode="paper")


def _no_evidence(_strategy_id: str) -> PromotionEvidence | None:
    return None


def _no_entry_evidence(_mint: str) -> EntryEvidence | None:
    return None


def _candidate(mint: str) -> Event:
    """A recorded token_created event: a candidate the prefilter admits at START."""
    return Event(
        kind=EventKind.token_created,
        entity_id=mint,
        payload={
            "created_at": int(START) - 600,
            "first_trade_at": int(START) - 300,
            "unique_buyers": 10,
            "prerank": "0.8",
        },
        occurred_at=format_ts_utc(START),
    )


async def _settle() -> None:
    """Yield until every task the desk spawned has finished. Virtual time does not move."""
    current = asyncio.current_task()
    for _ in range(_SETTLE_ROUNDS):
        pending = {task for task in asyncio.all_tasks() if task is not current and not task.done()}
        if not pending:
            return
        await asyncio.wait(pending)
    raise AssertionError("desk tasks did not settle")


async def _build(
    tmp_path: Path,
    *,
    grok: RecordingGrok,
    strategies: Sequence[Strategy],
    evidence: EvidenceSource,
) -> EventDesk:
    return await build_event_desk(
        _settings(),
        data_dir=tmp_path / "desk",
        clock=FixtureClock(START),
        rpc_transport=ReadOnlyDouble(),
        grok_transport=grok,
        strategies=strategies,
        evidence=evidence,
        entry_evidence=_no_entry_evidence,
    )


async def test_recorded_events_run_through_every_edge_and_exhaust_the_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    grok = RecordingGrok()
    evidence_calls: list[str] = []

    def evidence(strategy_id: str) -> PromotionEvidence | None:
        evidence_calls.append(strategy_id)
        return None

    desk = await _build(tmp_path, grok=grok, strategies=(ScriptedStrategy(),), evidence=evidence)
    try:
        await desk.start()

        # Bus -> Grok gateway -> LayeredBudget. An ordinary caller may spend the minute limit (6)
        # less its reserve (20%, two calls): four calls reach the transport, and the fifth
        # candidate is refused by the budget before any transport call.
        for mint in CANDIDATE_MINTS:
            await desk.publish(_candidate(mint))
        await _settle()
        assert len(grok.texts) == 4
        assert desk.budget.try_charge(reserve_priority=False) is False

        # Runtime -> router. Autonomy is manual-ticket, so the router refuses and journals.
        await desk.run_ticks(
            (
                TickSnapshot(
                    mint=CANDIDATE_MINTS[0],
                    ts=START + 1,
                    launch_ts=START - 600,
                    price_lamports=1_000,
                    unique_buyers=10,
                    curve_progress=0.1,
                ),
            )
        )
        store = desk.root.store
        refusal_key = f"route-refusal|{STRATEGY}|{DECISION}|autonomy_manual_ticket"
        assert store.by_key(refusal_key) is not None
        assert store.read(types=["OrderPlaced", "FillRecorded"], limit=None) == []

        # Ledger -> promotion feed -> evaluator. A PositionOpened row attributes the ticket to the
        # strategy; the PositionClosed row appended after it is the trigger.
        opened = PositionOpened(
            source="paper",
            mint=POSITION_MINT,
            price_entry=Decimal("1"),
            token_units=1_000,
            cost_basis_lamports=SIZE,
            opened_ts_utc=format_ts_utc(START),
            ticket_id=TICKET,
        ).model_dump(mode="json")
        append_with_ticket_ref(
            store,
            {
                "ts_utc": format_ts_utc(START),
                "source": "paper",
                "correlation_id": "desk",
                "idempotency_key": "e2e-open",
                "type": "PositionOpened",
                "payload": opened,
            },
            ticket_id=TICKET,
            strategy_id=STRATEGY,
        )
        closed = PositionClosed(
            source="paper",
            mint=POSITION_MINT,
            price_exit=Decimal("2"),
            proceeds_lamports=SIZE * 2,
            realized_pnl_lamports=SIZE,
            reason="take_profit",
        ).model_dump(mode="json")
        store.append(
            ts_utc=format_ts_utc(START + 2),
            source="paper",
            correlation_id="desk",
            idempotency_key="e2e-close",
            type="PositionClosed",
            payload=closed,
        )
        await desk.publish(
            Event(
                kind=EventKind.position_closed,
                entity_id=POSITION_MINT,
                payload={"reason": "take_profit"},
                occurred_at=format_ts_utc(START + 2),
            )
        )
        await _settle()
        assert evidence_calls == [STRATEGY]
    finally:
        await desk.close()


@pytest.mark.parametrize("mode", ["live", "replay", "manual"])
async def test_non_paper_desk_is_refused_before_any_io(tmp_path: Path, mode: str) -> None:
    settings = _settings().model_copy(update={"mode": mode})

    with pytest.raises(ValueError):
        await build_event_desk(
            settings,
            data_dir=tmp_path / "desk",
            clock=FixtureClock(START),
            rpc_transport=ReadOnlyDouble(),
            grok_transport=RecordingGrok(),
            strategies=(),
            evidence=_no_evidence,
            entry_evidence=_no_entry_evidence,
        )

    assert not (tmp_path / "desk").exists()
