"""One event catalog. Priority is a function of kind. Ids include occurred_at."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from pumpgrok.core.idempotency import canonical_json

Priority = Literal[0, 1, 2]


class EventKind(StrEnum):
    """v4 bus kinds. Fixture `tick` is not a member."""

    kill_switch = "kill_switch"
    halt = "halt"
    exit_signal = "exit_signal"
    risk_veto = "risk_veto"
    token_created = "token_created"
    migration = "migration"
    trade = "trade"
    position_opened = "position_opened"
    position_closed = "position_closed"
    strategy_intent = "strategy_intent"
    curve_tick = "curve_tick"
    mark = "mark"


PRIORITY_BY_KIND: dict[EventKind, Priority] = {
    EventKind.kill_switch: 0,
    EventKind.halt: 0,
    EventKind.exit_signal: 0,
    EventKind.risk_veto: 0,
    EventKind.token_created: 1,
    EventKind.migration: 1,
    EventKind.trade: 1,
    EventKind.position_opened: 1,
    EventKind.position_closed: 1,
    EventKind.strategy_intent: 1,
    EventKind.curve_tick: 2,
    EventKind.mark: 2,
}


def priority_of(kind: EventKind) -> Priority:
    """Total function of kind. A missing kind raises KeyError. Callers cannot set this."""
    return PRIORITY_BY_KIND[kind]


def _without_correlation(payload: Mapping[str, Any]) -> dict[str, Any]:
    stripped: dict[str, Any] = {}
    for key, value in payload.items():
        if key == "correlation_id":
            continue
        if isinstance(value, dict):
            stripped[key] = _without_correlation(value)
        else:
            stripped[key] = value
    return stripped


def derive_event_id(
    kind: EventKind,
    entity_id: str,
    payload: Mapping[str, Any],
    occurred_at: str,
) -> str:
    """sha256 prefix of kind, entity_id, payload, and required occurred_at.

    correlation_id is excluded. Two identical payloads at different occurred_at
    values are different ids.
    """
    body = {
        "kind": str(kind),
        "entity_id": entity_id,
        "payload": _without_correlation(payload),
        "occurred_at": occurred_at,
    }
    digest = hashlib.sha256(canonical_json(body).encode()).hexdigest()
    return digest[:32]


class Event(BaseModel):
    """Frozen bus event. `event_id` and priority are not caller fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: EventKind
    entity_id: str
    payload: dict[str, Any]
    occurred_at: str
    correlation_id: str | None = None
    lamports: int | None = Field(default=None, strict=True)
    size_lamports: int | None = Field(default=None, strict=True)
    fee_lamports: int | None = Field(default=None, strict=True)
    token_units: int | None = Field(default=None, strict=True)
    event_id: str = Field(default="", init=False)

    def __init__(self, **data: Any) -> None:
        payload = data.get("payload", {})
        if isinstance(payload, Mapping):
            canonical_json({"payload": _without_correlation(dict(payload))})
        super().__init__(**data)
        object.__setattr__(
            self,
            "event_id",
            derive_event_id(self.kind, self.entity_id, self.payload, self.occurred_at),
        )
