"""INV-R-29: replay determinism; missing LLM record fails the run.

Owning tests for SAFETY_INVARIANTS.md section 3.4 row INV-R-29. Two
replays of the same dataset and seed give identical events.hash sha256,
identical exported JSONL bytes and an identical final LedgerState; a
different seed differs. Replay ledger ts_utc comes from the fixture,
every event has source=replay, and a missing LLM record for a
canonical request hash FAILS the run instead of falling back to rules.
Companion file tests/replay/test_runner_determinism.py proves the same
engine under different names; these are the matrix owners.

Harness: run_replay on synthetic datasets with FixtureClock-derived
stamps; no wall clock, no network.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pumpgrok.config.settings import FilterSettings
from pumpgrok.core.errors import ReplayMissingRecord
from pumpgrok.core.idempotency import canonical_json
from pumpgrok.ledger.export import export_ledger
from pumpgrok.ledger.reducer import initial_state, reduce
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import parse_ts_utc
from pumpgrok.replay.fixtures import load_dataset
from pumpgrok.replay.runner import ledger_events_hash, run_replay

T0 = "2026-01-01T00:00:00.000Z"
T1 = "2026-01-01T00:00:15.000Z"


def _tick(ts: str) -> dict[str, object]:
    return {
        "ts_utc": ts,
        "kind": "tick",
        "mint": "MintAAAA1111111111111111111111111111111111",
        "S": 42000000000,
        "T": 764608076000000,
        "complete": False,
        "source": "rest",
    }


def _write_dataset(root: Path, name: str, events: list[dict[str, object]]) -> Path:
    dataset = root / name
    dataset.mkdir(parents=True)
    files = {"events.jsonl": "".join(json.dumps(event) + "\n" for event in events)}
    manifest = {
        "dataset": name,
        "recorded_from_utc": events[0]["ts_utc"],
        "recorded_to_utc": events[-1]["ts_utc"],
        "seed_hint": 20260101,
        "sources": {"rest": "hand-authored"},
        "sha256": {
            filename: hashlib.sha256(data.encode("utf-8")).hexdigest()
            for filename, data in files.items()
        },
        "notes": "synthetic INV-R-29 determinism dataset",
    }
    for filename, data in files.items():
        (dataset / filename).write_text(data, encoding="utf-8")
    (dataset / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return dataset


def _journal_bytes(ledger: Path, out: Path) -> bytes:
    store = LedgerStore(str(ledger))
    try:
        export_ledger(store, journal_dir=out, trades_path=out / "trades.jsonl")
    finally:
        store.close()
    return b"".join(
        path.read_bytes() for path in sorted(out.glob("*.jsonl")) if path.name != "trades.jsonl"
    )


def _final_state(ledger: Path) -> str:
    store = LedgerStore(str(ledger))
    try:
        state = initial_state(source="replay", initial_equity_lamports=0, day_utc="2026-01-01")
        for event in store.read(since_seq=1, limit=None):
            state = reduce(state, event)
        return canonical_json(state.model_dump(mode="json"))
    finally:
        store.close()


def test_two_runs_identical(tmp_path: Path) -> None:
    """INV-R-29: same dataset plus seed gives identical hashes, bytes, state."""
    dataset = _write_dataset(tmp_path, "twin", [_tick(T0), _tick(T1)])
    first = run_replay(dataset, FilterSettings(), ledger_path=tmp_path / "a.sqlite")
    second = run_replay(dataset, FilterSettings(), ledger_path=tmp_path / "b.sqlite")
    assert first.events_hash == second.events_hash
    assert first.events_hash == ledger_events_hash(tmp_path / "a.sqlite")
    assert _journal_bytes(tmp_path / "a.sqlite", tmp_path / "ja") == _journal_bytes(
        tmp_path / "b.sqlite", tmp_path / "jb"
    )
    assert _final_state(tmp_path / "a.sqlite") == _final_state(tmp_path / "b.sqlite")
    # Fixture time rides every row: row epochs land on fixture stamps (the
    # clock formats microseconds while the fixture writes millis).
    store = LedgerStore(str(tmp_path / "a.sqlite"))
    try:
        stamps = load_dataset(dataset).events
        rows = store.read(limit=None)
        stamp_epochs = {parse_ts_utc(str(event["ts_utc"])) for event in stamps}
        row_epochs = {parse_ts_utc(str(row["ts_utc"])) for row in rows}
        assert row_epochs <= stamp_epochs
        assert {row["source"] for row in rows} == {"replay"}
    finally:
        store.close()
    other = run_replay(dataset, FilterSettings(), seed=20270101, ledger_path=tmp_path / "c.sqlite")
    assert other.events_hash != first.events_hash


def test_missing_llm_record_fails_replay(tmp_path: Path) -> None:
    """INV-R-29: an unrecorded model request fails the run, naming the hash."""
    dataset = _write_dataset(tmp_path, "no-llm-hit", [_tick(T0), _tick(T1)])
    llm_rows = [
        {
            "request_hash": "0" * 64,
            "outcome": "ok",
            "latency_s": 0.5,
            "response": {"verdict": "skip"},
        }
    ]
    (dataset / "llm.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in llm_rows), encoding="utf-8"
    )
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    manifest["sha256"]["llm.jsonl"] = hashlib.sha256(
        (dataset / "llm.jsonl").read_bytes()
    ).hexdigest()
    (dataset / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with pytest.raises(ReplayMissingRecord) as excinfo:
        run_replay(dataset, FilterSettings(), ledger_path=tmp_path / "miss.sqlite")
    assert excinfo.value.fields["request_hash"] != "0" * 64
    assert len(excinfo.value.fields["request_hash"]) == 64
    assert not (tmp_path / "miss.sqlite").exists()
