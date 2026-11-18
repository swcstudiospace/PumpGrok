"""Event desk composition root (RT-03, criterion 10).

:func:`build_event_desk` composes one paper desk over the live-data paper root
(:func:`build_live_paper_root`). It adds the event bus, the strategy runtime, the Grok gateway
over a layered budget, the intent router, the promotion evaluator and the entry gate. Any
settings object whose effective mode is not paper is refused before any I/O.

What wakes what:

- The bus is the wake. A delivered ``token_created`` event admits one candidate to the Grok
  gateway. Every delivered event then hands the promotion evaluator the ledger rows of
  TRIGGER_TYPES appended since its last look. The desk starts no timer.
- The strategy runtime runs on the injected fixture clock. Each Intent it produces reaches
  ``exec.place`` only through the intent router, and the router then looks at the feed too.
- Time moves only through the injected clock. Nothing here reads the host clock.

The transports, the strategies and the evidence sources are injected. The desk opens no
network connection of its own.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from pumpgrok.config.settings import Settings
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.tool import Tool
from pumpgrok.datafeed.readonly import ReadTransport
from pumpgrok.events.bus import EventBus
from pumpgrok.events.models import Event, EventKind
from pumpgrok.execution.entry_hook import EntryGate
from pumpgrok.grok.budget import LayeredBudget
from pumpgrok.grok.cache import ResponseCache
from pumpgrok.grok.gateway import Candidate, GrokGateway, GrokRequest, GrokTransport
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.promotion.evaluator import TRIGGER_TYPES, EvidenceSource, PromotionEvaluator
from pumpgrok.promotion.thresholds import load_thresholds
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.entry_checks import EntryEvidence, MintLists, evaluate_entry, load_mint_lists
from pumpgrok.strategies.allocation import slice_lamports
from pumpgrok.strategies.base import Intent, Strategy, TickSnapshot
from pumpgrok.strategies.runtime import StrategyRuntime
from pumpgrok.supervisor.intent_router import ExecPlace, IntentRouter
from pumpgrok.supervisor.live_paper import LivePaperRoot, build_live_paper_root
from pumpgrok.tools.exec.place import PlaceIn, build_place_tool
from pumpgrok.tools.safety.provider import paid_rpc_provider_recorded

if TYPE_CHECKING:
    from pumpgrok.config.sections.engine import SafetyThresholds
    from pumpgrok.execution.paper_adapter.models import CurveSnapshot

__all__ = [
    "ENTRY_CHECK_ENABLED",
    "EntryEvidenceSource",
    "EventDesk",
    "PromotionFeed",
    "SafetyEntryCheck",
    "build_event_desk",
]

#: TODO(owner): name and home of the one setting that gates the entry check into the live
#: adapter. The owner approved wiring it into the paper adapter, so it is on.
ENTRY_CHECK_ENABLED = True

#: Freshness bounds for the live-data root: the values datafeed.feed_loop defaults to.
DESK_MAX_AGE_S = 10.0
DESK_MAX_OBSERVATIONS = 4

#: Per-strategy exposure slice, in basis points of paper equity: the value the strategy replay uses.
DESK_SLICE_BPS = 2_000

#: Grok agent for candidate admission. The auditor is an ordinary caller, not a reserve caller.
CANDIDATE_AGENT = "auditor"
_CANDIDATE_PROMPT = "Admit or refuse one new token candidate for the event desk."
_CANDIDATE_PROMPT_SHA = hashlib.sha256(_CANDIDATE_PROMPT.encode()).hexdigest()
_CANDIDATE_SCHEMA = "desk.candidate.v1"

GROK_BUDGET_FILE = "grok-budget.sqlite"
GROK_CACHE_FILE = "grok-cache.sqlite"

#: The order fields exec.place accepts. The router also sends a correlation id, which it refuses.
_PLACE_FIELDS = (
    "ticket_id",
    "mint",
    "side",
    "decision_id",
    "size_lamports",
    "max_slippage_bps",
    "approval_id",
)

#: Safety evidence for one mint, or None when none has been produced.
EntryEvidenceSource = Callable[[str], EntryEvidence | None]


def _dead_letter(event: Event) -> None:
    """Refuse silently losing an event: a failed event stops the publish loudly."""
    raise RuntimeError(f"event desk has no dead-letter sink for {event.kind}")


class SafetyEntryCheck:
    """Entry check over the RSK-05 rules. A mint with no safety evidence is refused."""

    def __init__(
        self,
        *,
        evidence: EntryEvidenceSource,
        lists: MintLists,
        thresholds: SafetyThresholds,
    ) -> None:
        self._evidence = evidence
        self._lists = lists
        self._thresholds = thresholds

    def refusal(
        self,
        mint: str,
        _source: object,
        _snapshot: CurveSnapshot,
        *,
        holder_blind_advisory: bool,
    ) -> str | None:
        """Refusal detail for a BUY on ``mint``; None admits it."""
        evidence = self._evidence(mint)
        if evidence is None:
            return "no safety evidence for mint"
        verdict = evaluate_entry(
            evidence,
            self._lists,
            self._thresholds,
            holder_blind_advisory=holder_blind_advisory,
        )
        return None if verdict.ok else "; ".join(verdict.reasons)


class PromotionFeed:
    """Hands the evaluator each ledger row of TRIGGER_TYPES appended since its last look.

    The cursor starts after the trigger rows already in the ledger, so rows written before
    the desk started are not re-evaluated.
    """

    def __init__(self, store: LedgerStore, evaluator: PromotionEvaluator) -> None:
        self._store = store
        self._evaluator = evaluator
        existing = store.read(types=sorted(TRIGGER_TYPES), limit=None)
        self._next_seq = int(existing[-1]["seq"]) + 1 if existing else 0

    def drain(self) -> int:
        """Evaluate each new trigger row once, in seq order; return how many were read."""
        rows = self._store.read(since_seq=self._next_seq, types=sorted(TRIGGER_TYPES), limit=None)
        for row in rows:
            self._evaluator.handle(row)
            self._next_seq = int(row["seq"]) + 1
        return len(rows)


@dataclass(frozen=True)
class EventDesk:
    """The wired paper desk. Call :meth:`close` to settle the bus and release the stores."""

    root: LivePaperRoot
    bus: EventBus
    runtime: StrategyRuntime
    gateway: GrokGateway
    budget: LayeredBudget
    router: IntentRouter
    promotion: PromotionEvaluator
    feed: PromotionFeed
    entry_gate: EntryGate

    async def start(self) -> None:
        await self.bus.start()

    async def publish(self, event: Event) -> None:
        await self.bus.publish(event)

    async def run_ticks(self, ticks: Sequence[TickSnapshot]) -> None:
        await self.runtime.run(ticks)

    async def close(self) -> None:
        try:
            await self.bus.shutdown()
        finally:
            self.root.close()


async def build_event_desk(
    settings: Settings,
    *,
    data_dir: Path,
    clock: FixtureClock,
    rpc_transport: ReadTransport,
    grok_transport: GrokTransport,
    strategies: Sequence[Strategy],
    evidence: EvidenceSource,
    entry_evidence: EntryEvidenceSource,
) -> EventDesk:
    """Build the paper event desk. Refusals come first and do no I/O.

    Raises ValueError, before any I/O, for an effective mode other than ``"paper"``, and for
    an absent RPC endpoint (the live root refuses it).
    The holder-pair flag is read here: it is True while no paid RPC provider is recorded.
    """
    if settings.effective_mode != "paper":
        raise ValueError("event desk builds in paper mode only")
    entry_gate = _entry_gate(settings, entry_evidence)
    endpoint = settings.rpc.endpoints[0] if settings.rpc.endpoints else ""
    root = await build_live_paper_root(
        mode="paper",
        endpoint=endpoint,
        transport=rpc_transport,
        clock=clock,
        rng_seed=settings.replay.seed,
        data_dir=data_dir,
        budget=settings.risk,
        limits=settings.limits,
        max_age_s=DESK_MAX_AGE_S,
        max_observations=DESK_MAX_OBSERVATIONS,
        entry_gate=entry_gate if ENTRY_CHECK_ENABLED else None,
    )
    try:
        return _compose(
            settings,
            root,
            data_dir=data_dir,
            clock=clock,
            grok_transport=grok_transport,
            strategies=strategies,
            evidence=evidence,
            entry_gate=entry_gate,
        )
    except BaseException:
        root.close()
        raise


def _entry_gate(settings: Settings, entry_evidence: EntryEvidenceSource) -> EntryGate:
    """The entry gate: the safety check plus the holder-pair flag, read once at build."""
    check = SafetyEntryCheck(
        evidence=entry_evidence,
        lists=load_mint_lists(),
        thresholds=settings.safety.thresholds,
    )
    return EntryGate(
        check=check,
        holder_blind_advisory=not paid_rpc_provider_recorded(),
    )


def _compose(
    settings: Settings,
    root: LivePaperRoot,
    *,
    data_dir: Path,
    clock: FixtureClock,
    grok_transport: GrokTransport,
    strategies: Sequence[Strategy],
    evidence: EvidenceSource,
    entry_gate: EntryGate,
) -> EventDesk:
    """Wire the edges over the live root. Every collaborator is built or injected here."""
    rng = make_rng(settings.replay.seed)
    ids = IdFactory(clock, rng)
    router = IntentRouter(
        exec_place=_exec_place(build_place_tool(root.adapter, lambda: settings.risk, clock)),
        risk=root.risk,
        store=root.store,
        clock=clock,
        ids=ids,
        slices=slice_lamports(
            settings.risk.paper_equity_lamports,
            {strategy.strategy_id: DESK_SLICE_BPS for strategy in strategies},
        ),
        max_slippage_bps=settings.limits.max_slippage_bps,
    )
    promotion = PromotionEvaluator(root.store, evidence=evidence, thresholds=load_thresholds())
    feed = PromotionFeed(root.store, promotion)
    budget = LayeredBudget(data_dir / GROK_BUDGET_FILE, clock)
    cache = ResponseCache(data_dir / GROK_CACHE_FILE, clock)
    gateway = GrokGateway(clock=clock, transport=grok_transport, cache=cache, budget=budget)
    model = settings.grok.fast_model

    async def on_event(event: Event) -> None:
        if event.kind is EventKind.token_created:
            await gateway.admit(_candidate_request(event, model))
        feed.drain()

    async def route(intents: tuple[Intent, ...]) -> None:
        for intent in intents:
            await router.route(intent)
        feed.drain()

    bus = EventBus(
        clock=clock,
        handler=on_event,
        dlq=_dead_letter,
        rng=make_rng(settings.replay.seed),
    )
    runtime = StrategyRuntime(clock=clock, strategies=tuple(strategies), sink=route)
    return EventDesk(
        root=root,
        bus=bus,
        runtime=runtime,
        gateway=gateway,
        budget=budget,
        router=router,
        promotion=promotion,
        feed=feed,
        entry_gate=entry_gate,
    )


def _candidate_request(event: Event, model: str) -> GrokRequest:
    """One Grok admission request for a ``token_created`` event.

    The payload carries ``created_at``, ``first_trade_at``, ``unique_buyers`` and ``prerank``.
    """
    payload = event.payload
    candidate = Candidate(
        mint=event.entity_id,
        created_at=float(payload["created_at"]),
        first_trade_at=float(payload["first_trade_at"]),
        unique_buyers=int(payload["unique_buyers"]),
        prerank=Decimal(str(payload["prerank"])),
    )
    return GrokRequest(
        event_id=event.event_id,
        agent=CANDIDATE_AGENT,
        model=model,
        prompt_sha=_CANDIDATE_PROMPT_SHA,
        schema=_CANDIDATE_SCHEMA,
        input={"unique_buyers": candidate.unique_buyers},
        text=f"candidate {candidate.mint}",
        candidate=candidate,
    )


def _exec_place(place: Tool) -> ExecPlace:
    """Adapt the router's order dict to the typed exec.place tool."""

    async def exec_place(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            order = PlaceIn.model_validate({key: payload[key] for key in _PLACE_FIELDS})
        except ValidationError:
            return {
                "status": "rejected",
                "reason": "invalid_order",
                "ticket_id": str(payload.get("ticket_id", "")),
            }
        return dict((await place(order)).model_dump())

    return exec_place
