"""Deterministic replay tracer (paper-engine.md 4.4-4.5, PAPER-004).

Two seeded runs over the same fixture must produce identical hashes,
identical ledgers and a CONSISTENT chain: the clock, RNG and ULIDs all derive
from fixture stamps plus seed, never from host time.
"""

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from pumpgrok.config.settings import FilterSettings
from pumpgrok.core.errors import DataStale, ReplayMissingRecord
from pumpgrok.ledger.store import LedgerInconsistent, LedgerStore
from pumpgrok.replay.runner import ledger_events_hash, run_replay

SMOKE = Path(__file__).resolve().parents[1] / "fixtures" / "replay" / "smoke"


def _rows(ledger: Path) -> list[tuple[object, ...]]:
    conn = sqlite3.connect(str(ledger))
    try:
        return [
            tuple(row)
            for row in conn.execute(
                "SELECT seq, ts_utc, source, correlation_id,"
                " idempotency_key, type, payload_json, prev_hash, hash"
                " FROM events ORDER BY seq ASC;"
            ).fetchall()
        ]
    finally:
        conn.close()


def test_two_seeded_runs_produce_identical_hashes(tmp_path: Path) -> None:
    first = run_replay(SMOKE, FilterSettings(), ledger_path=tmp_path / "a.sqlite")
    second = run_replay(SMOKE, FilterSettings(), ledger_path=tmp_path / "b.sqlite")

    assert first.events_hash == second.events_hash
    assert first.events_hash == ledger_events_hash(tmp_path / "a.sqlite")
    assert _rows(tmp_path / "a.sqlite") == _rows(tmp_path / "b.sqlite")


def test_replay_ledger_verifies_consistent_and_holds_one_verdict(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    result = run_replay(SMOKE, FilterSettings(), ledger_path=ledger)

    store = LedgerStore(ledger)
    try:
        assert store.verify() is True
    finally:
        store.close()
    (row,) = _rows(ledger)
    assert row[2] == "replay"
    assert row[5] == "JournalNote"
    assert result.events_read == 4
    assert result.seq == 1


def test_different_seed_produces_different_hashes(tmp_path: Path) -> None:
    base = run_replay(SMOKE, FilterSettings(), ledger_path=tmp_path / "a.sqlite")
    other = run_replay(SMOKE, FilterSettings(), seed=20270101, ledger_path=tmp_path / "b.sqlite")
    assert base.events_hash != other.events_hash


def _write_dataset(
    root: Path, name: str, events: list[dict[str, object]], llm: list[dict[str, object]] | None
) -> Path:
    dataset = root / name

    dataset.mkdir(parents=True)
    files = {"events.jsonl": "".join(json.dumps(event) + "\n" for event in events)}
    if llm is not None:
        files["llm.jsonl"] = "".join(json.dumps(record) + "\n" for record in llm)
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
        "notes": "synthetic determinism-test dataset",
    }
    for filename, data in files.items():
        (dataset / filename).write_text(data, encoding="utf-8")
    (dataset / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return dataset


def _tick(ts: str, mint: str = "MintAAAA1111111111111111111111111111111111") -> dict[str, object]:
    return {
        "ts_utc": ts,
        "kind": "tick",
        "mint": mint,
        "S": 42000000000,
        "T": 764608076000000,
        "complete": False,
        "source": "rest",
    }


def test_180s_silence_fails_the_run_with_data_stale(tmp_path: Path) -> None:
    dataset = _write_dataset(
        tmp_path,
        "gapped",
        [_tick("2026-01-01T00:00:00.000Z"), _tick("2026-01-01T00:03:00.000Z")],
        None,
    )
    with pytest.raises(DataStale, match="silence budget"):
        run_replay(dataset, FilterSettings(), ledger_path=tmp_path / "gap.sqlite")
    assert not (tmp_path / "gap.sqlite").exists()


def test_missing_llm_record_fails_the_run(tmp_path: Path) -> None:
    dataset = _write_dataset(
        tmp_path,
        "no-llm-hit",
        [_tick("2026-01-01T00:00:00.000Z"), _tick("2026-01-01T00:00:15.000Z")],
        [
            {
                "request_hash": "0" * 64,
                "outcome": "ok",
                "latency_s": 0.5,
                "response": {"verdict": "skip"},
            }
        ],
    )
    with pytest.raises(ReplayMissingRecord, match="no recorded LLM outcome"):
        run_replay(dataset, FilterSettings(), ledger_path=tmp_path / "miss.sqlite")


def test_verify_failure_removes_the_created_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WR-07: an append/verify failure removes the just-created ledger file."""
    target = tmp_path / "bad.sqlite"
    monkeypatch.setattr(LedgerStore, "verify", lambda self: False)
    with pytest.raises(LedgerInconsistent, match="replay ledger failed verification"):
        run_replay(SMOKE, FilterSettings(), ledger_path=target)
    assert not target.exists()
    assert not Path(str(target) + "-wal").exists()
    assert not Path(str(target) + "-shm").exists()
