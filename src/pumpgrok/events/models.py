"""One event catalog. Priority is a function of kind. Ids include occurred_at."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Mapping
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    PlainValidator,
    model_validator,
)

from pumpgrok.core.idempotency import canonical_json

Priority = Literal[0, 1, 2]


class EventKind(StrEnum):
    """v4 bus kinds. Fixture `tick` is not a member."""

    kill_switch = "kill_switch"
    halt = "halt"
    exit_signal = "exit_signal"
    risk_veto = "risk_veto"
    token_created = "token_created"  # noqa: S105 - event kind, not a credential
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


class FrozenPayload(Mapping[str, Any]):
    """Read-only payload. Nested dicts are FrozenPayload; nested lists are tuples.

    Data access is __getitem__, __iter__ and __len__. The Mapping mixin supplies
    the rest. There are no mutator methods.
    """

    __slots__ = ("_data",)

    def __init__(self, data: Mapping[str, Any]) -> None:
        self._data: dict[str, Any] = {key: _freeze(value) for key, value in data.items()}

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)


def _freeze(value: object) -> Any:
    """Recursively wrap mappings as FrozenPayload and sequences as tuples."""
    if isinstance(value, Mapping):
        return FrozenPayload(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: object) -> Any:
    """Inverse of _freeze: mappings become dict, tuples and lists become list."""
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def _validate_payload(value: object) -> FrozenPayload:
    """Freeze a caller mapping. Unserializable leaves raise TypeError via canonical_json."""
    if isinstance(value, FrozenPayload):
        return value
    if not isinstance(value, Mapping):
        raise ValueError("payload must be a mapping")
    frozen = FrozenPayload(value)
    canonical_json({"payload": _canonical_for_id(frozen)})
    return frozen


def _thaw_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Plain dict and list for model_dump in python and json modes."""
    return {key: _thaw(item) for key, item in payload.items()}


_PayloadField = Annotated[
    FrozenPayload,
    PlainValidator(_validate_payload, json_schema_input_type=dict[str, Any]),
    PlainSerializer(_thaw_payload, return_type=dict[str, Any]),
]


def _canonical_for_id(value: Any) -> Any:
    """Hash body: correlation_id is dropped at every depth. Mappings hash as dicts, tuples as lists.

    Keys are not reordered here. canonical_json sorts keys recursively.
    """
    if isinstance(value, Mapping):
        return {k: _canonical_for_id(v) for k, v in value.items() if k != "correlation_id"}
    if isinstance(value, (list, tuple)):
        return [_canonical_for_id(v) for v in value]
    return value


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
        "payload": _canonical_for_id(dict(payload)),
        "occurred_at": occurred_at,
    }
    digest = hashlib.sha256(canonical_json(body).encode()).hexdigest()
    return digest[:32]


class Event(BaseModel):
    """Frozen bus event. `event_id` and priority are not caller fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: EventKind
    entity_id: str
    payload: _PayloadField
    occurred_at: str
    correlation_id: str | None = None
    lamports: int | None = Field(default=None, strict=True)
    size_lamports: int | None = Field(default=None, strict=True)
    fee_lamports: int | None = Field(default=None, strict=True)
    token_units: int | None = Field(default=None, strict=True)
    event_id: str = Field(default="", init=False)

    @model_validator(mode="after")
    def _derive_event_id(self) -> Self:
        object.__setattr__(
            self,
            "event_id",
            derive_event_id(self.kind, self.entity_id, self.payload, self.occurred_at),
        )
        return self
