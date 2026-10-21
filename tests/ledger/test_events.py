"""Task RED: 18 R32 event models and schema export."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.ledger.events import (
    EVENT_MODELS,
    EventType,
    JournalNote,
    event_json_schemas,
)


def test_all_18_models_validate_and_forbid_extra() -> None:
    assert len(EventType) == 18
    assert len(EVENT_MODELS) == 18
    seen_types = set()
    for event_type in EventType:
        model = EVENT_MODELS[event_type]
        kwargs = {"source": "paper"}
        for name, field in model.model_fields.items():
            if name == "source":
                continue
            if field.is_required():
                annotation = str(field.annotation)
                if "note_kind" in name or "NoteKind" in annotation:
                    kwargs[name] = "note"
                elif "Decimal" in annotation:
                    kwargs[name] = "1.5"
                elif "int" in annotation:
                    kwargs[name] = 1
                elif "list" in annotation.lower() or "List" in annotation:
                    kwargs[name] = []
                elif "bool" in annotation:
                    kwargs[name] = True
                else:
                    kwargs[name] = "x"
        instance = model(**kwargs)
        assert instance.source in ("paper", "replay", "manual")
        seen_types.add(event_type.value)
        with pytest.raises(ValidationError):
            model(**{**kwargs, "bogus_extra_field": 1})
    assert len(seen_types) == 18


def test_journal_note_kind_note_ok_halt_rejected() -> None:
    note = JournalNote(source="replay", seat="desk", note_kind="note", text="skip")
    assert note.seat == "desk" and note.note_kind == "note"
    with pytest.raises(ValidationError):
        JournalNote(source="replay", seat="desk", note_kind="halt", text="nope")


def test_money_int_and_decimal_string_price() -> None:
    from pumpgrok.ledger.events import FillRecorded

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


def test_schema_export_produces_18_valid_schemas() -> None:
    schemas = event_json_schemas()
    assert len(schemas) == 18
    for name, schema in schemas.items():
        assert isinstance(schema, dict)
        assert schema.get("type") == "object"
        assert isinstance(schema.get("properties"), dict)
