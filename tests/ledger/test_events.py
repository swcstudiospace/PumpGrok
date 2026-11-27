"""Task RED: 20 event models (18 R32 plus the strategy kill pair) and schema export."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.ledger.events import (
    EVENT_MODELS,
    EventType,
    FillRecorded,
    JournalNote,
    event_json_schemas,
)


def _filler_value(name: str, field: Any) -> Any:
    annotation = str(field.annotation)
    if "note_kind" in name or "NoteKind" in annotation:
        return "note"
    if name == "side" or "Literal" in annotation:
        # B02a typed side as Side Literal["buy", "sell"]; "x" would fail.
        return "buy"
    if "Decimal" in annotation:
        return "1.5"
    if "int" in annotation:
        return 1
    if "list" in annotation.lower() or "List" in annotation:
        return []
    if "bool" in annotation:
        return True
    return "x"


def _model_kwargs(model: type[BaseModel]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"source": "paper"}
    for name, field in model.model_fields.items():
        if name == "source":
            continue
        if field.is_required():
            kwargs[name] = _filler_value(name, field)
    return kwargs


def test_all_21_models_validate_and_forbid_extra() -> None:
    assert len(EventType) == 21
    assert len(EVENT_MODELS) == 21
    seen_types = set()
    for event_type in EventType:
        model = EVENT_MODELS[event_type]
        kwargs = _model_kwargs(model)
        instance = model(**kwargs)
        assert instance.source in ("paper", "replay", "manual")
        seen_types.add(event_type.value)
        with pytest.raises(ValidationError):
            model(**{**kwargs, "bogus_extra_field": 1})
    assert len(seen_types) == 21


def test_journal_note_kind_note_ok_halt_rejected() -> None:
    note = JournalNote(source="replay", seat="desk", note_kind="note", text="skip")
    assert note.seat == "desk" and note.note_kind == "note"
    with pytest.raises(ValidationError):
        JournalNote(source="replay", seat="desk", note_kind="halt", text="nope")


def test_money_int_and_decimal_string_price() -> None:
    fill = FillRecorded(
        source="paper",
        order_id="x",
        decision_id="y",
        side="buy",
        mint="z",
        filled_lamports=100,
        filled_units=50,
        filled_fraction="0.5",
        price_avg="1.25",
    )
    assert fill.filled_lamports == 100
    with pytest.raises(ValidationError):
        FillRecorded(
            source="paper",
            order_id="x",
            decision_id="y",
            side="buy",
            mint="z",
            filled_lamports=100.5,
            filled_units=50,
            filled_fraction="0.5",
            price_avg="1.25",
        )
    with pytest.raises(ValidationError):
        FillRecorded(
            source="paper",
            order_id="x",
            decision_id="y",
            side="buy",
            mint="z",
            filled_lamports=100,
            filled_units=50,
            filled_fraction="0.5",
            price_avg=1.25,
        )


def test_schema_export_produces_21_valid_schemas() -> None:
    schemas = event_json_schemas()
    assert len(schemas) == 21
    for _name, schema in schemas.items():
        assert isinstance(schema, dict)
        assert schema.get("type") == "object"
        assert isinstance(schema.get("properties"), dict)
