"""The 18 R32 event models (paper-engine.md 3.3, FOUND-013).

Complete vocabulary: contracts/events/<snake>.schema.json generation (plan 01-07)
consumes :func:`event_json_schemas`. Money is integer base units (R28):
``<x>_lamports`` for SOL, ``<x>_units`` for token base units; prices and
fractions are :class:`~decimal.Decimal` parsed from strings with a ``price_``
(or ``*_fraction``/``*_pct``) name and never copied from vendor float prices
(R28). Every model is strict and ``extra=forbid`` (T-01-43): float money or a
float price raises instead of coercing.

Seat chatter is a :class:`JournalNote` payload; RUG alerts are
:class:`Escalation` payloads with ``kind="rug_alert"``.

ROSTER divergence (locked Q4): ``JournalNote.note_kind`` follows
paper-engine.md 3.3 — ``lead/whale/social/signal/verdict/safety_report/review
/ticket/note`` — with no ``halt`` value. The ROSTER ``halt`` kind is out of
scope for Phase 1. Skip-cycle rows use ``seat="desk"`` with
``note_kind="note"`` (locked discretion; ``MIGRATION_MAP``'s ``cycle`` is not
in the enum).
"""

from __future__ import annotations

import re
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EventSource = Literal["paper", "replay", "manual"]


class _StrictForbid(BaseModel):
    """Strict, closed models: no coercion, no unknown fields."""

    model_config = ConfigDict(extra="forbid", strict=True)


class EventType(StrEnum):
    """The 18 CamelCase R32 event types."""

    OrderPlaced = "OrderPlaced"
    OrderRejected = "OrderRejected"
    FillRecorded = "FillRecorded"
    PositionOpened = "PositionOpened"
    PositionClosed = "PositionClosed"
    MarkToMarket = "MarkToMarket"
    HaltSet = "HaltSet"
    HaltCleared = "HaltCleared"
    KillSwitchSet = "KillSwitchSet"
    KillSwitchCleared = "KillSwitchCleared"
    BreakerTripped = "BreakerTripped"
    BreakerReset = "BreakerReset"
    DailyRollover = "DailyRollover"
    ConfigChanged = "ConfigChanged"
    LiveWriteAttempted = "LiveWriteAttempted"
    Escalation = "Escalation"
    JournalNote = "JournalNote"
    ApprovalRecorded = "ApprovalRecorded"


class NoteKind(StrEnum):
    """JournalNote kinds per paper-engine.md 3.3 (no halt; locked Q4)."""

    lead = "lead"
    whale = "whale"
    social = "social"
    signal = "signal"
    verdict = "verdict"
    safety_report = "safety_report"
    review = "review"
    ticket = "ticket"
    note = "note"


class OrderPlaced(_StrictForbid):
    """Buy/sell intent accepted for placement (PaperAdapter.place)."""

    source: EventSource
    order_id: str
    decision_id: str
    ticket_id: str
    side: str = Field(description="buy | sell")
    mint: str
    slippage_bps: int
    size_lamports: int | None = None
    token_units: int | None = None
    quote_json: str = ""
    approval_json: str = ""
    risk_json: str = ""


class OrderRejected(_StrictForbid):
    """Buy/sell intent refused (adapter, RiskEngine, or LiveGate)."""

    source: EventSource
    order_id: str
    decision_id: str
    reason: str = Field(description="R34 ids + section 2.8 reasons")
    detail: str
    stage: str = Field(description="ACCEPTED | CONFIRMING")
    fees_lamports: int = 0


class FillRecorded(_StrictForbid):
    """Execution fill; partials carry filled_fraction < 1 (no OrderPartial)."""

    source: EventSource
    order_id: str
    decision_id: str
    side: str = Field(description="buy | sell")
    mint: str
    filled_lamports: int
    filled_units: int
    filled_fraction: Decimal
    price_avg: Decimal = Field(description="Decimal string, lamports per token base unit")
    venue_fee_lamports: int = 0
    network_cost_lamports: int = 0
    cash_delta_lamports: int = 0
    latency_s: Decimal = Decimal("0")
    venue_tx_ref: str = ""


class PositionOpened(_StrictForbid):
    """First buy fill opened a position."""

    source: EventSource
    mint: str
    price_entry: Decimal = Field(description="Decimal string, lamports per token base unit")
    token_units: int
    cost_basis_lamports: int
    opened_ts_utc: str
    symbol: str = ""
    creator: str = ""
    ticket_id: str = ""
    score: Decimal = Decimal("0")


class PositionClosed(_StrictForbid):
    """Sell fill zeroed the position (or a force-close did)."""

    source: EventSource
    mint: str
    price_exit: Decimal = Field(description="Decimal string, lamports per token base unit")
    proceeds_lamports: int
    realized_pnl_lamports: int
    reason: str = Field(
        description="stop_loss | take_profit | trailing_stop | max_hold | rug_alert"
        " | kill_flatten | blind_flatten | graduated | manual"
    )
    pnl_pct: Decimal = Decimal("0")
    hold_seconds: int = 0
    venue_tx_ref: str = ""


class MarkToMarket(_StrictForbid):
    """Periodic mark snapshot (journal seat / RiskEngine)."""

    source: EventSource
    ts_source: str
    cash_lamports: int
    equity_lamports: int
    unrealized_lamports: int
    prices_json: str = ""


class HaltSet(_StrictForbid):
    """Trading halted (RiskEngine only, R24)."""

    source: EventSource
    reason: str = Field(description="daily_loss | drawdown | ledger_inconsistent | manual")
    detail: str
    equity_lamports: int
    day_start_equity_lamports: int
    set_by: str = "risk_engine"


class HaltCleared(_StrictForbid):
    """Halt cleared by a human via CLI."""

    source: EventSource
    reason: str
    cleared_by: str = Field(description='"human:<name>" required')
    approval_id: str = ""
    note: str = ""


class KillSwitchSet(_StrictForbid):
    """Kill switch engaged (RiskEngine / risk.kill_switch)."""

    source: EventSource
    origin: str = Field(description="spec `source`: env | file | alert_command | tool")
    reason: str
    flatten_requested: bool = False
    set_by: str = ""


class KillSwitchCleared(_StrictForbid):
    """Kill switch cleared by a human via CLI."""

    source: EventSource
    cleared_by: str = Field(description='"human:<name>"')
    approval_id: str = ""
    sources_now_clear: list[str] = []


class BreakerTripped(_StrictForbid):
    """Risk breaker tripped."""

    source: EventSource
    breaker: str = Field(description="data_stale | loss_velocity | exec_errors")
    metric: str
    threshold: str
    cooldown_s: int


class BreakerReset(_StrictForbid):
    """Risk breaker reset after cooldown/probe."""

    source: EventSource
    breaker: str
    after_s: int
    probe_ok: bool = False


class DailyRollover(_StrictForbid):
    """UTC day boundary totals (RiskEngine)."""

    source: EventSource
    day_utc: str
    day_start_equity_lamports: int
    prior_day_json: str = ""
    open_positions: list[str] = []


class ConfigChanged(_StrictForbid):
    """Effective config diff applied at startup or via `state autonomy`."""

    source: EventSource
    by: str
    keys_changed: list[str] = []
    old_hash: str = ""
    new_hash: str = ""


class LiveWriteAttempted(_StrictForbid):
    """A live-write path was reached and refused (LiveAdapter / registry)."""

    source: EventSource
    adapter: str
    method: str
    caller_seat: str
    gate_result_json: str = ""
    stack_hash: str = ""


class Escalation(_StrictForbid):
    """Supervisor/RiskEngine/seat escalation; RUG alerts use kind=rug_alert."""

    source: EventSource
    kind: str = Field(
        description="bot_restart_exhausted | heartbeat_stale | persistence_down"
        " | clock_skew | ledger_inconsistent | blind_flatten | graduated | rug_alert"
    )
    seat: str
    detail: str


class JournalNote(_StrictForbid):
    """Seat journal entry; the skip cycle uses seat=desk, note_kind=note."""

    source: EventSource
    seat: str = "desk"
    note_kind: NoteKind = NoteKind.note
    text: str
    refs: list[str] = []


class ApprovalRecorded(_StrictForbid):
    """Human approval captured (interfaces.md 2.9); consumption is a second row."""

    source: EventSource
    id: str
    kind: str
    approved_by: str
    at: str
    ticket_id: str = ""
    mint: str = ""
    size_lamports: int = 0
    max_slippage_bps: int = 0
    exit_rule_id: str = ""
    raw_message: str = ""
    consumed: bool = False


EVENT_MODELS: dict[EventType, type[_StrictForbid]] = {
    EventType.OrderPlaced: OrderPlaced,
    EventType.OrderRejected: OrderRejected,
    EventType.FillRecorded: FillRecorded,
    EventType.PositionOpened: PositionOpened,
    EventType.PositionClosed: PositionClosed,
    EventType.MarkToMarket: MarkToMarket,
    EventType.HaltSet: HaltSet,
    EventType.HaltCleared: HaltCleared,
    EventType.KillSwitchSet: KillSwitchSet,
    EventType.KillSwitchCleared: KillSwitchCleared,
    EventType.BreakerTripped: BreakerTripped,
    EventType.BreakerReset: BreakerReset,
    EventType.DailyRollover: DailyRollover,
    EventType.ConfigChanged: ConfigChanged,
    EventType.LiveWriteAttempted: LiveWriteAttempted,
    EventType.Escalation: Escalation,
    EventType.JournalNote: JournalNote,
    EventType.ApprovalRecorded: ApprovalRecorded,
}

_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


def event_type_to_snake(event_type: EventType) -> str:
    """CamelCase type to snake_case contract file stem (OrderPlaced -> order_placed)."""
    return _CAMEL_BOUNDARY.sub("_", event_type.value).lower()


EVENT_TYPE_SNAKE: dict[EventType, str] = {t: event_type_to_snake(t) for t in EventType}


def event_json_schemas() -> dict[str, dict]:
    """Export one JSON Schema per R32 type, keyed by snake_case name.

    Consumed by plan 01-07 ``contracts/events/<snake>.schema.json`` generation.
    """
    return {event_type_to_snake(t): m.model_json_schema() for t, m in EVENT_MODELS.items()}


def model_json_schema() -> dict[str, dict]:
    """Alias of :func:`event_json_schemas` for plan 01-07 consumers."""
    return event_json_schemas()
