"""Event-mode golden hashes are pinned and deterministic."""

import hashlib
import json
from pathlib import Path

from pumpgrok.core.idempotency import canonical_json
from pumpgrok.events.models import Event, EventKind
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.scheduler.event_cycles import run_wake
from pumpgrok.supervisor.scheduler.wake import dispatch

GOLDEN_HASHES = {
    "smoke": "e31e667ce4209036edac5f3f03f260ea317fa44d218e831babf494d661043f5e",
    "smoke-10m": "888e1849dca763a0ecbc088e873969f5c8da7fee63031bca7310f58203f2204c",
    "soak-3d": "c08ad0ddddfd44de00590c9fc2f5f80b6852aa428e3d05ec1f4d26d8a7194e70",
}


def _events(name: str) -> list[Event]:
    rows = [
        json.loads(line)
        for line in Path(f"tests/fixtures/replay/{name}/events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    events: list[Event] = []
    for row in rows:
        try:
            kind = EventKind(row["kind"]) if row["kind"] != "tick" else EventKind.curve_tick
        except (ValueError, KeyError):
            kind = EventKind.curve_tick
        payload = {k: v for k, v in row.items() if k not in {"kind", "mint", "ts_utc"}}
        events.append(
            Event(
                kind=kind,
                entity_id=str(row.get("mint", "x")),
                payload=payload,
                occurred_at=str(row.get("ts_utc", "2026-01-01T00:00:00.000000Z")),
            )
        )
    return events


def _golden(name: str) -> str:
    wakes = dispatch(_events(name), clock=FixtureClock(0.0))
    results = run_wake(wakes, clock=FixtureClock(0.0))
    body = [{"seat": r.seat, "kind": r.kind, "entity_id": r.entity_id} for r in results]
    return hashlib.sha256(canonical_json({"results": body}).encode()).hexdigest()


def test_smoke_golden_hash() -> None:
    assert _golden("smoke") == GOLDEN_HASHES["smoke"]


def test_soak_golden_hash() -> None:
    assert _golden("soak-3d") == GOLDEN_HASHES["soak-3d"]


def test_cadence_golden_hash_is_pinned_on_disk() -> None:
    pin_text = Path("tests/replay/pin_support.py").read_text(encoding="utf-8")
    assert "b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" in pin_text
