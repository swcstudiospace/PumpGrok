"""The 18 R32 event models (paper-engine.md 3.3, FOUND-013).

Complete vocabulary: contracts/events/<snake>.schema.json generation (plan 01-07)
consumes :func:`event_json_schemas`. Money is integer base units (R28):
``<x>_lamports`` for SOL, ``<x>_units`` for token base units; prices and
fractions are :class:`~decimal.Decimal` parsed from strings with a ``price_``
(or ``*_fraction``/``*_pct``) name and never copied from vendor float prices
(R28). Every model forbids extras (T-01-43) and every value field is strict:
float money or a float price raises instead of coercing.

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
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

EventSource = Literal["paper", "replay", "manual"]


def _reject_float(value: Any) -> Any:
    """Refuse float leaves before Decimal parsing (R28: money is int, ratios are Decimal)."""
    if isinstance(value, float):
        raise ValueError("float leaves are forbidden (money is int, ratios are Decimal)")
    return value


MoneyInt = Annotated[int, Field(strict=True)]
StrictBool = Annotated[bool, Field(strict=True)]
PriceDecimal = Annotated[Decimal, BeforeValidator(_reject_float)]


class _ClosedModel(BaseModel):
    """Closed models: unknown fields rejected (T-01-43)."""

    model_config = ConfigDict(extra="forbid")


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


class OrderPlaced(_ClosedModel):
    """Buy/sell intent accepted for placement (PaperAdapter.place)."""

    source: EventSource
    order_id: str
    decision_id: str
    ticket_id: str
    side: str = Field(description="buy | sell")
    mint: str
    slippage_bps: MoneyInt
    size_lamports: MoneyInt | None = None
    token_units: MoneyInt | None = None
    quote_json: str = ""
    approval_json: str = ""
    risk_json: str = ""


class OrderRejected(_ClosedModel):
    """Buy/sell intent refused (adapter, RiskEngine, or LiveGate)."""

    source: EventSource
    order_id: str
    decision_id: str
    reason: str = Field(description="R34 ids + section 2.8 reasons")
    detail: str
    stage: str = Field(description="ACCEPTED | CONFIRMING")
    fees_lamports: MoneyInt = 0


class FillRecorded(_ClosedModel):
    """Execution fill; partials carry filled_fraction < 1 (no OrderPartial)."""

    source: EventSource
    order_id: str
    decision_id: str
    side: str = Field(description="buy | sell")
    mint: str
    filled_lamports: MoneyInt
    filled_units: MoneyInt
    filled_fraction: PriceDecimal
    price_avg: PriceDecimal = Field(description="Decimal string, lamports per token base unit")
    venue_fee_lamports: MoneyInt = 0
    network_cost_lamports: MoneyInt = 0
    cash_delta_lamports: MoneyInt = 0
    latency_s: PriceDecimal = Decimal("0")
    venue_tx_ref: str = ""


class PositionOpened(_ClosedModel):
    """First buy fill opened a position."""

    source: EventSource
    mint: str
    price_entry: PriceDecimal = Field(description="Decimal string, lamports per token base unit")
    token_units: MoneyInt
    cost_basis_lamports: MoneyInt
    opened_ts_utc: str
    symbol: str = ""
    creator: str = ""
    ticket_id: str = ""
    score: PriceDecimal = Decimal("0")


class PositionClosed(_ClosedModel):
    """Sell fill zeroed the position (or a force-close did)."""

    source: EventSource
    mint: str
    price_exit: PriceDecimal = Field(description="Decimal string, lamports per token base unit")
    proceeds_lamports: MoneyInt
    realized_pnl_lamports: MoneyInt
    reason: str = Field(
        description="stop_loss | take_profit | trailing_stop | max_hold | rug_alert"
        " | kill_flatten | blind_flatten | graduated | manual"
    )
    pnl_pct: PriceDecimal = Decimal("0")
    hold_seconds: MoneyInt = 0
    venue_tx_ref: str = ""


class MarkToMarket(_ClosedModel):
    """Periodic mark snapshot (journal seat / RiskEngine)."""

    source: EventSource
    ts_source: str
    cash_lamports: MoneyInt
    equity_lamports: MoneyInt
    unrealized_lamports: MoneyInt
    prices_json: str = ""


class HaltSet(_ClosedModel):
    """Trading halted (RiskEngine only, R24)."""

    source: EventSource
    reason: str = Field(description="daily_loss | drawdown | ledger_inconsistent | manual")
    detail: str
    equity_lamports: MoneyInt
    day_start_equity_lamports: MoneyInt
    set_by: str = "risk_engine"


class HaltCleared(_ClosedModel):
    """Halt cleared by a human via CLI."""

    source: EventSource
    reason: str
    cleared_by: str = Field(description='"human:<name>" required')
    approval_id: str = ""
    note: str = ""


class KillSwitchSet(_ClosedModel):
    """Kill switch engaged (RiskEngine / risk.kill_switch)."""

    source: EventSource
    origin: str = Field(description="spec `source`: env | file | alert_command | tool")
    reason: str
    flatten_requested: StrictBool = False
    set_by: str = ""


class KillSwitchCleared(_ClosedModel):
    """Kill switch cleared by a human via CLI."""

    source: EventSource
    cleared_by: str = Field(description='"human:<name>"')
    approval_id: str = ""
    sources_now_clear: list[str] = []


class BreakerTripped(_ClosedModel):
    """Risk breaker tripped."""

    source: EventSource
    breaker: str = Field(description="data_stale | loss_velocity | exec_errors")
    metric: str
    threshold: str
    cooldown_s: MoneyInt


class BreakerReset(_ClosedModel):
    """Risk breaker reset after cooldown/probe."""

    source: EventSource
    breaker: str
    after_s: MoneyInt
    probe_ok: StrictBool = False


class DailyRollover(_ClosedModel):
    """UTC day boundary totals (RiskEngine)."""

    source: EventSource
    day_utc: str
    day_start_equity_lamports: MoneyInt
    prior_day_json: str = ""
    open_positions: list[str] = []


class ConfigChanged(_ClosedModel):
    """Effective config diff applied at startup or via `state autonomy`."""

    source: EventSource
    by: str
    keys_changed: list[str] = []
    old_hash: str = ""
    new_hash: str = ""


class LiveWriteAttempted(_ClosedModel):
    """A live-write path was reached and refused (LiveAdapter / registry)."""

    source: EventSource
    adapter: str
    method: str
    caller_seat: str
    gate_result_json: str = ""
    stack_hash: str = ""


class Escalation(_ClosedModel):
    """Supervisor/RiskEngine/seat escalation; RUG alerts use kind=rug_alert."""

    source: EventSource
    kind: str = Field(
        description="bot_restart_exhausted | heartbeat_stale | persistence_down"
        " | clock_skew | ledger_inconsistent | blind_flatten | graduated | rug_alert"
    )
    seat: str
    detail: str


class JournalNote(_ClosedModel):
    """Seat journal entry; the skip cycle uses seat=desk, note_kind=note."""

    source: EventSource
    seat: str = "desk"
    note_kind: NoteKind = NoteKind.note
    text: str
    refs: list[str] = []


class ApprovalRecorded(_ClosedModel):
    """Human approval captured (interfaces.md 2.9); consumption is a second row."""

    source: EventSource
    id: str
    kind: str
    approved_by: str
    at: str
    ticket_id: str = ""
    mint: str = ""
    size_lamports: MoneyInt = 0
    max_slippage_bps: MoneyInt = 0
    exit_rule_id: str = ""
    raw_message: str = ""
    consumed: StrictBool = False


EVENT_MODELS: dict[EventType, type[_ClosedModel]] = {
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
